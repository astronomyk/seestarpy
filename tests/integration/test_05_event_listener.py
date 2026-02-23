"""Phase 5 — Event listener tests.

Verify that the event listener populates LATEST_STATE and LATEST_LOGS,
and that start/stop are idempotent.

Note: ``stop_listener()`` shuts down the background thread by setting
``_shutdown_event = None``, which causes the asyncio tasks to crash.
This is inherently racy, so tests that start/stop the listener multiple
times may need generous delays between cycles.
"""

import time

import pytest

from seestarpy.events import event_stream
from seestarpy.events.event_listener import start_listener, stop_listener

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def _listener_cleanup():
    """Ensure the listener is stopped and the old thread has time to die."""
    yield
    stop_listener()
    # Give the daemon thread time to release the TCP connection
    time.sleep(2)


def test_start_listener_populates_state(verified_connection):
    """Start the listener and wait up to 15 s for LATEST_STATE to be populated.

    The first heartbeat fires immediately on connection, but the Seestar
    may take several seconds to respond. We wait generously.
    """
    event_stream.LATEST_STATE.clear()

    start_listener(with_websocket=False)

    # Give the background thread time to connect and establish heartbeats
    deadline = time.time() + 15
    while time.time() < deadline:
        if event_stream.LATEST_STATE:
            break
        time.sleep(1)

    assert len(event_stream.LATEST_STATE) > 0, (
        "LATEST_STATE was not populated within 15 seconds"
    )


def test_latest_logs_is_populated(verified_connection):
    """After running the listener, LATEST_LOGS should have entries."""
    event_stream.LATEST_LOGS.clear()

    start_listener(with_websocket=False)

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


def test_start_listener_is_idempotent(verified_connection):
    """Calling start_listener twice should be a no-op on the second call."""
    start_listener(with_websocket=False)
    time.sleep(2)
    start_listener(with_websocket=False)  # Should be a no-op
