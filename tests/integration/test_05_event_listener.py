"""Phase 5 — Event listener tests.

Verify that the event listener populates LATEST_STATE and LATEST_LOGS,
and that start/stop are idempotent.

The Seestar only broadcasts events when it is actively doing something
(not parked and idle).  Tests that check for events open the scope arm
and trigger a filter wheel change to guarantee event traffic.
"""

import time

import pytest

from seestarpy import raw
from seestarpy.events import event_stream
from seestarpy.events.event_listener import start_listener, stop_listener

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="module")
def _open_scope(verified_connection):
    """Open the scope arm so the Seestar generates events."""
    raw.scope_move_to_horizon()
    time.sleep(20)
    yield
    raw.scope_park(True)
    time.sleep(20)


@pytest.fixture(autouse=True)
def _listener_cleanup():
    """Ensure the listener is stopped between tests."""
    yield
    stop_listener()


def _trigger_activity():
    """Trigger a filter wheel change to generate WheelMove events."""
    current = raw.get_wheel_position().get("result", 1)
    target = 2 if current == 1 else 1
    raw.set_wheel_position(target)


def test_start_listener_populates_state(verified_connection, _open_scope):
    """Start the listener, trigger activity, and verify LATEST_STATE is populated."""
    event_stream.LATEST_STATE.clear()

    start_listener(with_websocket=False)
    time.sleep(2)

    # Trigger a filter wheel change to generate events
    _trigger_activity()

    deadline = time.time() + 15
    while time.time() < deadline:
        if event_stream.LATEST_STATE:
            break
        time.sleep(1)

    assert len(event_stream.LATEST_STATE) > 0, (
        "LATEST_STATE was not populated within 15 seconds"
    )


def test_latest_logs_is_populated(verified_connection, _open_scope):
    """After running the listener with activity, LATEST_LOGS should have entries."""
    event_stream.LATEST_LOGS.clear()

    start_listener(with_websocket=False)
    time.sleep(2)

    _trigger_activity()

    deadline = time.time() + 15
    while time.time() < deadline:
        if event_stream.LATEST_LOGS:
            break
        time.sleep(1)

    assert len(event_stream.LATEST_LOGS) > 0, (
        "LATEST_LOGS was not populated within 15 seconds"
    )


def test_stop_listener_is_idempotent():
    """Calling stop_listener when not running should not raise."""
    stop_listener()  # Should be a no-op
    stop_listener()  # Still a no-op


def test_start_listener_is_idempotent(verified_connection, _open_scope):
    """Calling start_listener twice should be a no-op on the second call."""
    start_listener(with_websocket=False)
    time.sleep(2)
    start_listener(with_websocket=False)  # Should be a no-op
