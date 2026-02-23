"""Phase 6 — UI module tests.

All functions called without the ``ips`` kwarg (single-IP, no threading).
"""

import time

import pytest

from seestarpy import ui
from seestarpy import status

pytestmark = pytest.mark.integration


def test_exposure_get(verified_connection):
    """exposure() with no args should return the current exposure dict."""
    result = ui.exposure()
    assert isinstance(result, dict)
    assert "stack_l" in result


def test_exposure_set_and_restore(verified_connection):
    """Set exposure to 20 s, verify, then restore."""
    original = ui.exposure()
    original_val = original.get("stack_l")

    new_val = 20 if original_val != 20000 else 10
    ui.exposure(exptime=new_val)
    time.sleep(1)

    updated = ui.exposure()
    assert updated.get("stack_l") == new_val * 1000

    # Restore
    if original_val is not None:
        ui.exposure(exptime=original_val // 1000)


def test_filter_wheel_get(verified_connection):
    """filter_wheel() with no args should return the current filter position."""
    result = ui.filter_wheel()
    assert isinstance(result, dict)
    assert result.get("result") in {0, 1, 2}


def test_tracking_get(verified_connection):
    """tracking() with no args should return the current tracking state."""
    result = ui.tracking()
    assert isinstance(result, dict)


def test_focuser_get(verified_connection):
    """focuser() with no args should return the current focuser position."""
    result = ui.focuser()
    assert isinstance(result, dict)


@pytest.mark.slow
@pytest.mark.destructive
def test_open_and_close(verified_connection):
    """Open the arm, verify not parked, close, verify parked."""
    ui.open()
    time.sleep(20)

    parked = status.is_parked()
    assert parked is False, "Scope should be open (not parked)"

    ui.close()
    time.sleep(20)

    parked = status.is_parked()
    assert parked is True, "Scope should be parked after close()"
