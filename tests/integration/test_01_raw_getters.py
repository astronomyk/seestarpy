"""Phase 1 — Raw getter tests.

Parametrized tests over all no-argument getters plus targeted structure
checks for key responses.
"""

import pytest

from seestarpy import raw

pytestmark = pytest.mark.integration

# All simple no-arg getters that should return a dict with a 'method' key
SIMPLE_GETTERS = [
    "get_albums",
    "get_camera_info",
    "get_camera_state",
    "get_disk_volume",
    "get_focuser_position",
    "get_last_solve_result",
    "get_solve_result",
    "get_stacked_img",
    "get_stack_info",
    "get_sensor_calibration",
    "get_setting",
    "get_user_location",
    "get_view_state",
    "get_wheel_position",
    "get_wheel_setting",
    "iscope_get_app_state",
    "scope_get_equ_coord",
    "scope_get_horiz_coord",
    "scope_get_ra_dec",
    "scope_get_track_state",
    "pi_get_time",
    "pi_is_verified",
]


@pytest.mark.parametrize("getter_name", SIMPLE_GETTERS)
def test_simple_getter_returns_dict(getter_name, verified_connection):
    """Each no-arg getter should return a dict containing a 'method' key.

    Note: The Seestar's TCP connection occasionally delivers an event
    broadcast before the command response.  If the first attempt hits
    this race condition we retry once.
    """
    func = getattr(raw, getter_name)
    result = func()
    assert isinstance(result, dict), f"{getter_name} returned {type(result)}"

    if "method" not in result and "Event" in result:
        # Race condition: received an event broadcast instead of the
        # command response.  Retry once.
        result = func()
        assert isinstance(result, dict), f"{getter_name} retry returned {type(result)}"

    assert "method" in result, f"{getter_name} response missing 'method' key: {result}"


# ------------------------------------------------------------------
# Targeted structure tests
# ------------------------------------------------------------------

def test_get_device_state_no_keys(verified_connection):
    """Full device state tree should contain the major sections."""
    result = raw.get_device_state()
    assert isinstance(result, dict)
    payload = result.get("result", {})
    for section in ("device", "setting", "mount", "pi_status", "storage"):
        assert section in payload, f"Missing section: {section}"


def test_get_device_state_with_keys(verified_connection):
    """Filtered query should return only the requested sections."""
    result = raw.get_device_state(keys=["mount", "storage"])
    payload = result.get("result", {})
    assert "mount" in payload
    assert "storage" in payload


def test_get_camera_info_structure(verified_connection):
    """Camera info should contain chip_size (2-element list) and pixel_size_um."""
    result = raw.get_camera_info()
    payload = result.get("result", {})
    assert isinstance(payload.get("chip_size"), list)
    assert len(payload["chip_size"]) == 2
    assert "pixel_size_um" in payload


def test_get_setting_structure(verified_connection):
    """Settings response should contain exp_ms, stack_dither, auto_power_off, focal_pos."""
    result = raw.get_setting()
    payload = result.get("result", {})
    for key in ("exp_ms", "stack_dither", "auto_power_off", "focal_pos"):
        assert key in payload, f"Missing setting key: {key}"
