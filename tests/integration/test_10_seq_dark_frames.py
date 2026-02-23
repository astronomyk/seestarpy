"""Sequence 1 — Dark frame creation.

Tests ``start_create_dark()`` / ``stop_create_dark()``.  In normal use
the Seestar creates darks automatically when ``iscope_start_view`` is
called after an exposure change or power-on, so the remaining sequences
do NOT include an explicit dark step.

Flow::

    scope_move_to_horizon()  -> wait ScopeMoveToHorizon complete (30 s)
    start_create_dark()      -> wait DarkLibrary complete (180 s)
    scope_park()             -> wait ScopeHome complete (30 s)
"""

import pytest

from seestarpy import raw
from .conftest import wait_for_event

pytestmark = [
    pytest.mark.integration,
    pytest.mark.sequence,
    pytest.mark.slow,
    pytest.mark.usefixtures("event_listener_session", "module_safety_net"),
]


def test_move_to_horizon(verified_connection):
    """Open the arm and wait for ScopeMoveToHorizon to complete."""
    raw.scope_move_to_horizon()
    result = wait_for_event(
        "ScopeMoveToHorizon", {"complete"}, timeout=30,
    )
    assert result["state"] == "complete"


def test_create_dark_frames(verified_connection):
    """Create dark library and wait for DarkLibrary to complete."""
    raw.start_create_dark()
    result = wait_for_event(
        "DarkLibrary", {"complete", "fail"}, timeout=180,
    )
    assert result.get("percent") is not None or result.get("state") == "complete"


def test_park_after_darks(verified_connection):
    """Park the scope and wait for ScopeHome/ScopeMoveToHorizon to complete."""
    raw.scope_park()
    # Parking triggers a ScopeMoveToHorizon event (state=complete when arm closes)
    result = wait_for_event(
        "ScopeMoveToHorizon", {"complete"}, timeout=30,
    )
    assert result["state"] == "complete"
