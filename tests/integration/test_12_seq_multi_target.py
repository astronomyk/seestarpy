"""Sequence 3 — Multi-target observation.

Two circumpolar targets: Mizar (RA=13.4, Dec=54.9) and Polaris
(RA=2.53, Dec=89.26).

Flow::

    scope_move_to_horizon() -> wait complete

    TARGET 1 (Mizar):
    iscope_start_view(Mizar) -> wait AutoGoto complete (120 s)
    iscope_start_stack(restart=True) -> wait 3 stacked frames (120 s)
    iscope_stop_view() -> sleep 3 s

    TARGET 2 (Polaris):
    iscope_start_view(Polaris) -> wait AutoGoto complete (120 s)
    iscope_start_stack(restart=True) -> wait 3 stacked frames (120 s)
    iscope_stop_view()

    scope_park()
"""

import time

import pytest

from seestarpy import raw
from .conftest import wait_for_event, wait_for_stacked_frames

pytestmark = [
    pytest.mark.integration,
    pytest.mark.sequence,
    pytest.mark.slow,
    pytest.mark.usefixtures("event_listener_session", "module_safety_net"),
]

MIZAR_RA = 13.4
MIZAR_DEC = 54.9
POLARIS_RA = 2.53
POLARIS_DEC = 89.26


def test_move_to_horizon(verified_connection):
    """Open the arm before multi-target sequence."""
    raw.scope_move_to_horizon()
    result = wait_for_event(
        "ScopeMoveToHorizon", {"complete"}, timeout=30,
    )
    assert result["state"] == "complete"


# ---- TARGET 1: Mizar ----

def test_goto_mizar(verified_connection):
    """Slew to Mizar."""
    raw.iscope_start_view(
        ra=MIZAR_RA, dec=MIZAR_DEC, target_name="Mizar",
    )
    result = wait_for_event("AutoGoto", {"complete", "fail"}, timeout=120)
    assert result["state"] == "complete", f"AutoGoto failed: {result.get('error')}"


def test_stack_mizar(verified_connection):
    """Stack 3 frames on Mizar."""
    raw.iscope_start_stack(restart=True)
    result = wait_for_stacked_frames(min_frames=3, timeout=120)
    assert result.get("stacked_frame", 0) >= 3


def test_stop_view_mizar(verified_connection):
    """Stop viewing Mizar."""
    raw.iscope_stop_view()
    time.sleep(3)


# ---- TARGET 2: Polaris ----

def test_goto_polaris(verified_connection):
    """Slew to Polaris."""
    raw.iscope_start_view(
        ra=POLARIS_RA, dec=POLARIS_DEC, target_name="Polaris",
    )
    result = wait_for_event("AutoGoto", {"complete", "fail"}, timeout=120)
    assert result["state"] == "complete", f"AutoGoto failed: {result.get('error')}"


def test_stack_polaris(verified_connection):
    """Stack 3 frames on Polaris."""
    raw.iscope_start_stack(restart=True)
    result = wait_for_stacked_frames(min_frames=3, timeout=120)
    assert result.get("stacked_frame", 0) >= 3


def test_stop_view_and_park(verified_connection):
    """Stop viewing Polaris and park the scope."""
    raw.iscope_stop_view()
    time.sleep(3)

    raw.scope_park()
    result = wait_for_event(
        "ScopeMoveToHorizon", {"complete"}, timeout=30,
    )
    assert result["state"] == "complete"
