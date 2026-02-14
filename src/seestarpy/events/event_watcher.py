import asyncio
import json
import time
from typing import List, Type

from src.seestarpy.connection import DEFAULT_IP, DEFAULT_PORT, VERBOSE_LEVEL
from src.seestarpy.events import event_definitions as evs


class EventWatcher:
    """
    Async event watcher that collects Seestar events into typed dataclasses.

    Maintains a persistent TCP connection to the Seestar and
    deserialises each incoming JSON message into the corresponding
    :mod:`~seestarpy.events.event_definitions` dataclass.  New event
    types are added automatically on first occurrence; subsequent
    messages of the same type update the existing instance.

    .. note::
        This class is experimental and requires an active ``asyncio``
        event loop.  For most use cases, prefer :func:`start_listener`.
    """
    def __init__(self):
        self.events_list: List[evs.Event] = []
        self._task = asyncio.create_task(self._listen())

    async def _heartbeat(self, writer):
        while True:
            await asyncio.sleep(10)
            if writer is not None:
                heartbeat_msg = {"id": int(time.time()), "method": "scope_get_equ_coord"}
                data = json.dumps(heartbeat_msg) + "\r\n"
                writer.write(data.encode())
                await writer.drain()
                if VERBOSE_LEVEL >= 2:
                    print("[heartbeat] Sent:", heartbeat_msg)

    async def _listen(self):
        while True:
            try:
                print(f"Connecting to {DEFAULT_IP}:{DEFAULT_PORT}...")
                reader, writer = await asyncio.open_connection(DEFAULT_IP, DEFAULT_PORT)
                print(f"Connected to {DEFAULT_IP}:{DEFAULT_PORT}")

                hb_task = asyncio.create_task(self._heartbeat(writer))

                while True:
                    line = await reader.readuntil(separator=b"\r\n")
                    message = line.decode().strip()
                    try:
                        data = json.loads(message)
                        if VERBOSE_LEVEL >= 1:
                            print("[event]", data)
                        self._handle_event(data)
                    except json.JSONDecodeError:
                        if VERBOSE_LEVEL >= 1:
                            print("[non-json]", message)

            except (asyncio.IncompleteReadError, ConnectionResetError):
                print("Connection closed by Seestar. Will reconnect in 5 sec...")
            except Exception as e:
                print(f"Unexpected error: {e}")

            try:
                hb_task.cancel()
            except:
                pass

            await asyncio.sleep(3)

    def _handle_event(self, data: dict):
        event_type = data.get("Event")
        if event_type is None:
            return

        for evt in self.events_list:
            if evt.__class__.__name__ == event_type:
                evt.update(json.dumps(data))
                return

        ev_class = getattr(evs, event_type)
        new_event = ev_class(**json.dumps(data))
        self.events_list.append(new_event)
        if VERBOSE_LEVEL >= 1:
            print(f"[event_watcher] New event stored: {new_event.__class__.__name__}")
