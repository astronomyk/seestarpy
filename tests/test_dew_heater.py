"""Offline tests for ui.dew_heater()."""

from unittest.mock import patch

import pytest

from seestarpy import ui


def _setting(heater_enable=False):
    """A get_setting() reply carrying just the key dew_heater reads."""
    return {"result": {"heater_enable": heater_enable,
                       "focal_pos": 1580,
                       "temp_unit": "C"}}


class TestDewHeaterGet:
    @patch("seestarpy.raw.get_setting", return_value=_setting(True))
    def test_reports_on(self, _s):
        assert ui.dew_heater() is True

    @patch("seestarpy.raw.get_setting", return_value=_setting(False))
    def test_reports_off(self, _s):
        assert ui.dew_heater() is False

    @patch("seestarpy.raw.get_setting", return_value={"result": {}})
    def test_missing_key_reads_as_off(self, _s):
        """Firmware that omits heater_enable must not raise."""
        assert ui.dew_heater() is False

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_get_does_not_write(self, _g, m_set, m_out):
        ui.dew_heater()
        m_set.assert_not_called()
        m_out.assert_not_called()


class TestDewHeaterSet:
    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_on_uses_the_app_power_level(self, m_set, m_out):
        ui.dew_heater(True)
        assert m_set.call_args.kwargs["heater_enable"] is True
        assert m_out.call_args.kwargs == {"is_dew_on": True,
                                          "dew_heater_power":
                                              ui.APP_DEW_HEATER_POWER}

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_off_drops_power_to_zero(self, m_set, m_out):
        ui.dew_heater(False)
        assert m_set.call_args.kwargs["heater_enable"] is False
        assert m_out.call_args.kwargs == {"is_dew_on": False,
                                          "dew_heater_power": 0}

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_explicit_power_is_passed_through(self, m_set, m_out):
        ui.dew_heater(True, power=60)
        assert m_out.call_args.kwargs["dew_heater_power"] == 60

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_setting_power_implies_switching_on(self, m_set, m_out):
        ui.dew_heater(power=75)
        assert m_set.call_args.kwargs["heater_enable"] is True
        assert m_out.call_args.kwargs == {"is_dew_on": True,
                                          "dew_heater_power": 75}

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_writes_both_the_setting_and_the_output(self, m_set, m_out):
        """Which one the firmware honours is undocumented, so both are sent."""
        ui.dew_heater(True)
        assert m_set.call_count == 1
        assert m_out.call_count == 1

    @patch("seestarpy.raw.pi_output_set2", return_value={"code": 0})
    @patch("seestarpy.raw.set_setting")
    def test_returns_the_output_reply(self, m_set, m_out):
        assert ui.dew_heater(True) == {"code": 0}

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_power_ignored_when_switching_off(self, m_set, m_out):
        """An explicit level with enabled=False is harmless: state wins."""
        ui.dew_heater(False, power=50)
        assert m_out.call_args.kwargs["is_dew_on"] is False


class TestDewHeaterValidation:
    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    @pytest.mark.parametrize("bad", [-1, 101, 250])
    def test_power_out_of_range_raises(self, m_set, m_out, bad):
        with pytest.raises(ValueError, match=r"\[0, 100\]"):
            ui.dew_heater(True, power=bad)
        m_out.assert_not_called()

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_on_at_zero_power_raises(self, m_set, m_out):
        """The trap the bare raw call sets: on, but doing nothing."""
        with pytest.raises(ValueError, match="cold"):
            ui.dew_heater(True, power=0)
        m_out.assert_not_called()

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_power_zero_without_enabled_raises(self, m_set, m_out):
        """power=0 alone implies 'on', so it hits the same guard."""
        with pytest.raises(ValueError, match="cold"):
            ui.dew_heater(power=0)
        m_out.assert_not_called()

    @patch("seestarpy.raw.pi_output_set2")
    @patch("seestarpy.raw.set_setting")
    def test_nothing_is_written_when_validation_fails(self, m_set, m_out):
        with pytest.raises(ValueError):
            ui.dew_heater(True, power=500)
        m_set.assert_not_called()
