"""Unit tests for the firmware-tolerant behaviour of the raw.py wrappers
that a colleague reported failing on firmware v8.46.

- ``get_stack_setting``: the RPC method was removed at firmware v6.7; the
  wrapper now falls back to ``get_setting`` on ``code 103`` while still
  returning the native response on older firmware.
- ``scope_get_ra_dec``: on the command socket newer firmware rejects it;
  the wrapper falls back to ``scope_get_equ_coord`` on ``code 103``.
- ``get_stacked_img``: a port-4800 binary-stream method, deprecated on the
  command-socket wrapper with a redirect to seestarpy.stream.
"""

import warnings
from unittest.mock import patch

import pytest

from seestarpy import raw


class TestGetStackSetting:
    @patch("seestarpy.raw.send_command")
    def test_native_response_on_old_firmware(self, mock_send):
        """code 0 -> return the native get_stack_setting response, no fallback."""
        native = {"code": 0, "result": {"save_discrete_frame": False,
                                         "save_discrete_ok_frame": True,
                                         "light_duration_min": -1}}
        mock_send.return_value = native
        with pytest.warns(DeprecationWarning):
            out = raw.get_stack_setting()
        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0] == {"method": "get_stack_setting"}
        assert out == native

    @patch("seestarpy.raw.send_command")
    def test_falls_back_to_get_setting_on_103(self, mock_send):
        """code 103 -> transparently query get_setting instead."""
        mock_send.side_effect = [
            {"code": 103, "error": "method not found"},
            {"code": 0, "result": {"stack_lenhance": False}},
        ]
        with pytest.warns(DeprecationWarning):
            out = raw.get_stack_setting()
        assert mock_send.call_count == 2
        assert mock_send.call_args_list[0][0][0] == {"method": "get_stack_setting"}
        assert mock_send.call_args_list[1][0][0] == {"method": "get_setting"}
        assert out["result"] == {"stack_lenhance": False}


class TestScopeGetRaDec:
    @patch("seestarpy.raw.send_command")
    def test_native_when_supported(self, mock_send):
        mock_send.return_value = {"code": 0, "result": [1.0, 2.0]}
        out = raw.scope_get_ra_dec()
        assert mock_send.call_count == 1
        assert out["result"] == [1.0, 2.0]

    @patch("seestarpy.raw.send_command")
    def test_falls_back_to_equ_coord_on_103(self, mock_send):
        mock_send.side_effect = [
            {"code": 103, "error": "method not found"},
            {"code": 0, "result": [12.3, 45.6]},
        ]
        out = raw.scope_get_ra_dec()
        assert mock_send.call_count == 2
        assert mock_send.call_args_list[0][0][0] == {"method": "scope_get_ra_dec"}
        assert mock_send.call_args_list[1][0][0] == {"method": "scope_get_equ_coord"}
        assert out["result"] == [12.3, 45.6]


class TestGetStackedImg:
    @patch("seestarpy.raw.send_command", return_value={"code": 103})
    def test_emits_deprecation_pointing_to_stream(self, mock_send):
        with pytest.warns(DeprecationWarning, match="stream"):
            raw.get_stacked_img()
