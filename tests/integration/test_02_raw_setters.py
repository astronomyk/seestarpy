"""Phase 2 — Raw setter tests.

Each setter saves the original value, makes a change, verifies it, and
restores.  Dangerous commands (reboot, shutdown, sensor calibration,
scope_sync) are excluded.
"""

import time

import pytest

from seestarpy import raw
from .conftest import assert_success

pytestmark = [pytest.mark.integration, pytest.mark.destructive]


class TestSetSetting:
    """Toggle exp_ms.stack_l between 10 000 and 20 000 ms."""

    def test_set_and_restore_exposure(self, initial_settings):
        original = initial_settings.get("result", {}).get("exp_ms", {}).get("stack_l")
        new_val = 20000 if original != 20000 else 10000

        result = raw.set_setting(exp_ms={"stack_l": new_val})
        assert isinstance(result, dict)

        verify = raw.get_setting()
        assert verify.get("result", {}).get("exp_ms", {}).get("stack_l") == new_val

        # Restore
        raw.set_setting(exp_ms={"stack_l": original})
        restored = raw.get_setting()
        assert restored.get("result", {}).get("exp_ms", {}).get("stack_l") == original


class TestSetControlValue:
    """Set camera gain to 80 and verify."""

    def test_set_gain(self, verified_connection):
        result = raw.set_control_value(gain=80)
        assert isinstance(result, dict)


class TestSetUserLocation:
    """Save original location, set to known coords, restore."""

    def test_set_and_restore_location(self, verified_connection):
        original = raw.get_user_location()
        orig_result = original.get("result", {})

        # Set to a known location (Greenwich Observatory)
        result = raw.set_user_location(lat=51.4769, lon=-0.0005)
        assert isinstance(result, dict)

        # Restore original if available
        if isinstance(orig_result, dict):
            orig_lat = orig_result.get("lat")
            orig_lon = orig_result.get("lon")
            if orig_lat is not None and orig_lon is not None:
                raw.set_user_location(lat=orig_lat, lon=orig_lon)


class TestSetWheelPosition:
    """Save original filter position, set to 1 (IR-cut), verify, restore."""

    @pytest.mark.slow
    def test_set_and_restore_wheel(self, verified_connection):
        original = raw.get_wheel_position()
        orig_pos = original.get("result")

        result = raw.set_wheel_position(1)
        assert isinstance(result, dict)
        time.sleep(3)  # Wait for wheel movement

        verify = raw.get_wheel_position()
        assert verify.get("result") == 1

        # Restore
        if orig_pos is not None and orig_pos != 1:
            raw.set_wheel_position(orig_pos)
            time.sleep(3)


class TestPiSetTime:
    """Call pi_set_time with no args; verify code 0."""

    def test_set_time(self, verified_connection):
        result = raw.pi_set_time()
        assert_success(result)


class TestPiOutputSet2:
    """Set dew heater off with power 0."""

    def test_dew_heater_off(self, verified_connection):
        result = raw.pi_output_set2(is_dew_on=False, dew_heater_power=0)
        assert isinstance(result, dict)


class TestSetSequenceSetting:
    """Set sequence name and verify response."""

    def test_set_sequence_name(self, verified_connection):
        result = raw.set_sequence_setting(name="TestSequence")
        assert isinstance(result, dict)
