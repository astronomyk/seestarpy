"""Core fixtures and helpers for integration tests against a live Seestar."""

import time

import pytest

from seestarpy import raw
from seestarpy import connection as conn
from seestarpy.events import event_stream
from seestarpy.events.event_listener import start_listener, stop_listener


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def assert_success(result):
    """Assert that *result* is a successful JSON-RPC response (code 0)."""
    assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
    assert result.get("code") == 0, f"Expected code 0, got {result.get('code')}: {result}"


def assert_error(result, expected_code=None):
    """Assert that *result* is a JSON-RPC error response."""
    assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
    has_error = "error" in result or result.get("code", 0) != 0
    assert has_error, f"Expected error response, got: {result}"
    if expected_code is not None:
        assert result.get("code") == expected_code, (
            f"Expected error code {expected_code}, got {result.get('code')}"
        )


# ---------------------------------------------------------------------------
# wait_for_event — poll LATEST_STATE until a terminal state is reached
# ---------------------------------------------------------------------------

def wait_for_event(event_name, terminal_states, timeout=60, poll_interval=1.0):
    """Poll ``LATEST_STATE`` until *event_name* reaches a terminal state.

    Parameters
    ----------
    event_name : str
        Key in ``event_stream.LATEST_STATE`` (e.g. ``"ScopeMoveToHorizon"``).
    terminal_states : set[str]
        States that signal completion (e.g. ``{"complete", "fail"}``).
    timeout : float
        Maximum seconds to wait before raising ``TimeoutError``.
    poll_interval : float
        Seconds between polls.

    Returns
    -------
    dict
        The final event dictionary from ``LATEST_STATE``.

    Raises
    ------
    TimeoutError
        If the event does not reach a terminal state within *timeout*.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        entry = event_stream.LATEST_STATE.get(event_name, {})
        state = entry.get("state")
        if state in terminal_states:
            return entry
        time.sleep(poll_interval)

    current = event_stream.LATEST_STATE.get(event_name, {})
    raise TimeoutError(
        f"Timed out waiting for {event_name} to reach {terminal_states}. "
        f"Last state: {current}"
    )


def wait_for_stacked_frames(min_frames, timeout=120, poll_interval=2.0):
    """Poll ``LATEST_STATE["Stack"]`` until *min_frames* have been stacked.

    Returns
    -------
    dict
        The Stack event dictionary.

    Raises
    ------
    TimeoutError
        If the required frame count is not reached within *timeout*.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        entry = event_stream.LATEST_STATE.get("Stack", {})
        stacked = entry.get("stacked_frame", 0)
        if stacked >= min_frames:
            return entry
        time.sleep(poll_interval)

    current = event_stream.LATEST_STATE.get("Stack", {})
    raise TimeoutError(
        f"Timed out waiting for {min_frames} stacked frames. "
        f"Last Stack event: {current}"
    )


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def seestar_ip():
    """Return the IP address of the connected Seestar."""
    return conn.DEFAULT_IP


@pytest.fixture(scope="session")
def verified_connection():
    """Verify the Seestar is reachable via ``test_connection``.

    Fails fast if the device cannot be contacted.
    """
    result = raw.test_connection()
    assert isinstance(result, dict), f"test_connection failed: {result}"
    assert result.get("code") == 0, f"test_connection error: {result}"
    return result


@pytest.fixture(scope="session")
def event_listener_session():
    """Start the event listener for the whole test session.

    Waits up to 10 s for heartbeats to populate ``LATEST_STATE``, then
    yields.  Stops the listener on teardown.
    """
    start_listener(with_websocket=False)

    # Wait for heartbeats to populate state
    deadline = time.time() + 10
    while time.time() < deadline:
        if event_stream.LATEST_STATE:
            break
        time.sleep(0.5)

    yield event_stream.LATEST_STATE

    stop_listener()


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def initial_settings():
    """Capture ``get_setting()`` result for save/restore in setter tests."""
    return raw.get_setting()


@pytest.fixture(scope="module", autouse=False)
def module_safety_net():
    """Safety net: park the telescope on teardown regardless of test outcome.

    Apply to sequence test modules by marking them with::

        pytestmark = pytest.mark.usefixtures("module_safety_net")
    """
    yield
    try:
        raw.iscope_stop_view()
        time.sleep(5)
    except Exception:
        pass
    try:
        raw.scope_park()
        time.sleep(20)
    except Exception:
        pass
