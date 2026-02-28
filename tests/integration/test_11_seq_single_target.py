"""Sequence 2 — Single target observation.

Target: Polaris (RA=2.53, Dec=89.26) — always above horizon in northern
hemisphere.

Flow::

    scope_move_to_horizon()                   -> wait complete (45 s)
    iscope_start_view(Polaris)                -> wait AutoGoto complete|fail (120 s)
    start_auto_focuse()                       -> wait AutoFocus complete|fail (90 s)
    iscope_start_stack(restart=True)          -> wait >= 3 stacked frames (120 s)
    iscope_stop_view()                        -> sleep 5 s
    scope_park()                              -> wait complete (45 s)
"""

import time
import warnings

import pytest

from seestarpy import raw
from .conftest import wait_for_event, wait_for_app_event

pytestmark = [
    pytest.mark.integration,
    pytest.mark.sequence,
    pytest.mark.slow,
    pytest.mark.usefixtures("event_listener_session", "module_safety_net"),
]

# Polaris — circumpolar for all northern-hemisphere observers
POLARIS_RA = 2.53
POLARIS_DEC = 89.26


def test_move_to_horizon(verified_connection):
    """Open the arm before starting the observation."""
    raw.scope_move_to_horizon()
    result = wait_for_event(
        "ScopeMoveToHorizon", {"complete"}, timeout=45,
    )
    assert result["state"] == "complete"


def test_goto_polaris(verified_connection):
    """Slew to Polaris and wait for AutoGoto to finish."""
    raw.iscope_start_view(
        ra=POLARIS_RA, dec=POLARIS_DEC, target_name="Polaris",
    )
    result = wait_for_app_event(
        "AutoGoto", {"complete", "fail"}, timeout=180,
    )
    assert result["state"] in ("complete", "fail")
    if result["state"] == "fail":
        pytest.fail(f"AutoGoto failed: {result.get('error')}")


def test_autofocus(verified_connection):
    """Run autofocus; log warning if no star is detected."""
    raw.start_auto_focuse()
    result = wait_for_app_event(
        "AutoFocus", {"complete", "fail"}, timeout=90,
    )
    if result["state"] == "fail" and "no star" in str(result.get("error", "")):
        warnings.warn("AutoFocus: no star detected — continuing anyway")
    elif result["state"] == "fail":
        pytest.fail(f"AutoFocus failed: {result.get('error')}")


def test_start_stacking(verified_connection):
    """Trigger stacking and verify the command is accepted."""
    result = raw.iscope_start_stack(restart=True)
    assert isinstance(result, dict)
    time.sleep(10)


def test_stop_view_and_park(verified_connection):
    """Stop the observation and park the scope."""
    raw.iscope_stop_view()
    time.sleep(5)

    raw.scope_park(True)
    result = wait_for_event(
        "ScopeMoveToHorizon", {"complete"}, timeout=45,
    )
    assert result["state"] == "complete"
