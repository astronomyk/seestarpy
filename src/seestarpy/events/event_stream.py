# seestarpy/event_stream.py

from collections import deque

#: dict: Most recent event data keyed by event type (e.g.
#: ``"Stack"``, ``"PlateSolve"``).  Updated in real time by
#: :func:`handle_event` while the listener is running.
LATEST_STATE = {}

#: deque: Rolling buffer of the last 500 raw event dictionaries,
#: in chronological order.
LATEST_LOGS = deque(maxlen=500)


def handle_event(data: dict):
    """
    Route an incoming Seestar event into the shared state stores.

    Extracts the ``"Event"`` key from *data* and upserts the entry in
    :data:`LATEST_STATE`, so that each event type always holds the most
    recent message.  The full message is also appended to
    :data:`LATEST_LOGS`.

    Parameters
    ----------
    data : dict
        A JSON-parsed Seestar message that must contain an ``"Event"``
        key to be stored.  Messages without an ``"Event"`` key are
        silently ignored.
    """
    event_type = data.get("Event")
    if event_type:
        LATEST_STATE[event_type] = data
        LATEST_LOGS.append(data)
