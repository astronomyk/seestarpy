"""Unit tests for the USB-C port-role wrappers in raw.py.

The Seestar's USB-C port is dual-role: ``typec_mode='file'`` presents the
scope as a USB mass-storage gadget, ``typec_mode='net'`` makes it a USB
host driving an external Ethernet adapter.  ``usb_en_eth`` is a separate
master switch and the firmware does **not** couple the two — writing
``typec_mode`` alone leaves ``usb_en_eth`` latched at its previous value
(verified live on an S50 running firmware 8.46).  Every mode therefore has
to write both keys, or a ``file`` switch cannot undo a ``net`` switch.
"""

from unittest.mock import patch

import pytest

from seestarpy import raw


OK = {"jsonrpc": "2.0", "method": "set_setting", "result": 0, "code": 0, "id": 1}


class TestSetUsbMode:
    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_net_writes_both_keys(self, mock_send):
        out = raw.set_usb_mode("net")
        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0] == {
            "method": "set_setting",
            "params": {"usb_en_eth": True, "typec_mode": "net"},
        }
        assert out == OK

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_file_also_clears_usb_en_eth(self, mock_send):
        """Regression: 'file' must clear the master switch, not just the role.

        Writing only typec_mode leaves usb_en_eth True, so a scope switched
        to 'net' and back would report a mixed file/True state forever.
        """
        raw.set_usb_mode("file")
        assert mock_send.call_args[0][0]["params"] == {
            "usb_en_eth": False, "typec_mode": "file"}

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_modes_are_exact_reversals(self, mock_send):
        """The two payloads must differ in both keys, never just one."""
        raw.set_usb_mode("net")
        net = mock_send.call_args[0][0]["params"]
        raw.set_usb_mode("file")
        file_ = mock_send.call_args[0][0]["params"]
        assert set(net) == set(file_) == {"usb_en_eth", "typec_mode"}
        assert all(net[k] != file_[k] for k in net)

    @pytest.mark.parametrize("alias", ["file", "drive", "storage", "usb",
                                       "FILE", "Drive"])
    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_file_aliases(self, mock_send, alias):
        raw.set_usb_mode(alias)
        assert mock_send.call_args[0][0]["params"]["typec_mode"] == "file"

    @pytest.mark.parametrize("alias", ["net", "eth", "ethernet", "lan",
                                       "NET", "Ethernet"])
    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_net_aliases(self, mock_send, alias):
        raw.set_usb_mode(alias)
        assert mock_send.call_args[0][0]["params"]["typec_mode"] == "net"

    @pytest.mark.parametrize("bad", ["host", "network", "", "rndis", None, 42])
    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_rejects_unknown_modes_without_sending(self, mock_send, bad):
        """Firmware answers code 102 for these, so fail before the round-trip."""
        with pytest.raises(ValueError, match="Unknown USB mode"):
            raw.set_usb_mode(bad)
        assert mock_send.call_count == 0

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_only_the_two_documented_values_reach_the_firmware(self, mock_send):
        """No alias may leak through as its own typec_mode value."""
        for alias in ["drive", "storage", "usb", "eth", "ethernet", "lan"]:
            raw.set_usb_mode(alias)
            assert mock_send.call_args[0][0]["params"]["typec_mode"] in ("file", "net")


class TestGetUsbMode:
    @patch("seestarpy.raw.send_command")
    def test_reports_both_fields(self, mock_send):
        mock_send.return_value = {"code": 0, "result": {
            "typec_mode": "net", "usb_en_eth": True, "dark_mode": False}}
        assert raw.get_usb_mode() == {"typec_mode": "net", "usb_en_eth": True}
        assert mock_send.call_args[0][0] == {"method": "get_setting"}

    @patch("seestarpy.raw.send_command")
    def test_mixed_state_is_reported_verbatim(self, mock_send):
        """file + usb_en_eth True is what a one-key reversal used to leave."""
        mock_send.return_value = {"code": 0, "result": {
            "typec_mode": "file", "usb_en_eth": True}}
        assert raw.get_usb_mode() == {"typec_mode": "file", "usb_en_eth": True}

    @patch("seestarpy.raw.send_command")
    def test_missing_keys_are_none(self, mock_send):
        """Firmware too old to know the settings must not raise."""
        mock_send.return_value = {"code": 0, "result": {}}
        assert raw.get_usb_mode() == {"typec_mode": None, "usb_en_eth": None}


class TestNoNestedMultipleIps:
    """get/set_usb_mode must not call another @multiple_ips wrapper.

    A nested call re-resolves the inherited IP against AVAILABLE_IPS, which
    only holds the address discovered at import time, so targeting any other
    scope raised ValueError('max_workers must be greater than 0').
    """

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_set_does_not_call_set_setting(self, mock_send):
        with patch("seestarpy.raw.set_setting") as mock_set_setting:
            raw.set_usb_mode("net")
        mock_set_setting.assert_not_called()

    @patch("seestarpy.raw.send_command")
    def test_get_does_not_call_get_setting(self, mock_send):
        mock_send.return_value = {"code": 0, "result": {
            "typec_mode": "file", "usb_en_eth": False}}
        with patch("seestarpy.raw.get_setting") as mock_get_setting:
            raw.get_usb_mode()
        mock_get_setting.assert_not_called()

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_works_for_an_ip_absent_from_available_ips(self, mock_send):
        """The exact failure seen live: a scope not discovered via mDNS."""
        from seestarpy import connection as conn

        saved_ip, saved_avail = conn.DEFAULT_IP, dict(conn.AVAILABLE_IPS)
        try:
            conn.AVAILABLE_IPS.clear()
            conn.AVAILABLE_IPS["seestar.local"] = "192.168.1.82"
            conn.DEFAULT_IP = "192.168.1.81"          # never discovered
            raw.set_usb_mode("net")
        finally:
            conn.DEFAULT_IP = saved_ip
            conn.AVAILABLE_IPS.clear()
            conn.AVAILABLE_IPS.update(saved_avail)
        assert mock_send.call_count == 1
