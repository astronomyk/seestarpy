# seestarpy/event_stream.py

from collections import deque

# Shared memory for state and recent log lines
LATEST_STATE = {}
LATEST_LOGS = deque(maxlen=500)


def handle_event(data: dict):
    """
    Update LATEST_STATE and LATEST_LOGS with a new event.

    Parameters
    ----------
    data : dict
        JSON-parsed Seestar message
    """
    event_type = data.get("Event")
    if event_type:
        LATEST_STATE[event_type] = data
        LATEST_LOGS.append(data)
