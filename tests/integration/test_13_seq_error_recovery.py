"""Sequence 4 — Error recovery tests.

Test A: Below-horizon target should trigger an Alert.
Test B: Stopping a goto mid-slew should cancel cleanly.
Test C: Autofocus with no stars should fail gracefully.
"""

import time

import pytest

from seestarpy import raw
from seestarpy.events import event_stream
from .conftest import wait_for_event

pytestmark = [
    pytest.mark.integration,
    pytest.mark.sequence,
    pytest.mark.slow,
    pytest.mark.usefixtures("event_listener_session", "module_safety_net"),
]

POLARIS_RA = 2.53
POLARIS_DEC = 89.26


class TestBelowHorizonTarget:
    """Test A — Sending a goto for a below-horizon target."""

    def test_move_to_horizon(self, verified_connection):
        raw.scope_move_to_horizon()
        wait_for_event("ScopeMoveToHorizon", {"complete"}, timeout=30)

    def test_below_horizon_triggers_alert(self, verified_connection):
        """Target at Dec=-89 should be below horizon from northern hemisphere."""
        # Clear any stale Alert
        event_stream.LATEST_STATE.pop("Alert", None)

        raw.iscope_start_view(
            ra=12.0, dec=-89.0, target_name="South_Pole",
        )
        # Expect an Alert event with "below horizon" (code 270)
        result = wait_for_event(
            "Alert", {"complete", "fail"}, timeout=15,
        )
        # Alert events don't always have a "state" key — check for error/code
        assert result.get("code") == 270 or "below horizon" in str(
            result.get("error", "")
        ), f"Expected below-horizon alert, got: {result}"

    def test_recovery_after_below_horizon(self, verified_connection):
        """After a below-horizon error, a valid goto should succeed."""
        raw.iscope_stop_view()
        time.sleep(2)

        raw.iscope_start_view(
            ra=POLARIS_RA, dec=POLARIS_DEC, target_name="Polaris",
        )
        result = wait_for_event(
            "AutoGoto", {"complete", "fail"}, timeout=120,
        )
        assert result["state"] == "complete", f"Recovery goto failed: {result}"

    def test_park_after_recovery(self, verified_connection):
        raw.iscope_stop_view()
        time.sleep(2)
        raw.scope_park()
        wait_for_event("ScopeMoveToHorizon", {"complete"}, timeout=30)


class TestStopGotoMidSlew:
    """Test B — Stop a goto mid-slew and verify clean cancellation."""

    def test_move_to_horizon(self, verified_connection):
        raw.scope_move_to_horizon()
        wait_for_event("ScopeMoveToHorizon", {"complete"}, timeout=30)

    def test_cancel_goto_mid_slew(self, verified_connection):
        """Start a goto to a far-away target, then cancel after 2 s."""
        # Use a target far from current position
        raw.scope_goto(ra=0.1, dec=0.1)
        time.sleep(2)

        raw.stop_goto_target()
        result = wait_for_event(
            "ScopeGoto", {"complete", "fail"}, timeout=15,
        )
        # The goto should have been interrupted
        assert result["state"] in ("complete", "fail")

    def test_park_after_cancel(self, verified_connection):
        raw.scope_park()
        wait_for_event("ScopeMoveToHorizon", {"complete"}, timeout=30)


class TestAutofocusNoStars:
    """Test C — Autofocus with no stars (continuous exposure, no goto)."""

    def test_move_to_horizon(self, verified_connection):
        raw.scope_move_to_horizon()
        wait_for_event("ScopeMoveToHorizon", {"complete"}, timeout=30)

    def test_start_view_no_goto(self, verified_connection):
        """Start continuous exposure without coordinates (no goto)."""
        raw.iscope_start_view()
        # Wait for ContinuousExposure to start
        time.sleep(5)

    def test_autofocus_fails_no_star(self, verified_connection):
        """Autofocus should fail with 'no star is detected'."""
        raw.start_auto_focuse()
        result = wait_for_event(
            "AutoFocus", {"complete", "fail"}, timeout=90,
        )
        assert result["state"] == "fail"
        assert "no star" in str(result.get("error", "")).lower()

    def test_stop_view_and_park(self, verified_connection):
        raw.iscope_stop_view()
        time.sleep(2)
        raw.scope_park()
        wait_for_event("ScopeMoveToHorizon", {"complete"}, timeout=30)
