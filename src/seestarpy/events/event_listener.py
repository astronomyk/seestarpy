import asyncio
import json
import time
import websockets
import threading
from pathlib import Path

from ..connection import DEFAULT_IP, DEFAULT_PORT, VERBOSE_LEVEL
from .event_stream import handle_event, LATEST_STATE

HEARTBEAT_INTERVAL = 3
_listener_running = False  # Prevent multiple starts
_shutdown_event = None
_listener_thread = None
_loop = None  # asyncio event loop running in the listener thread

connected_clients = set()


async def heartbeat(writer):
    """
    Send periodic heartbeat messages to keep the TCP connection alive.

    Cycles through several query methods (``get_device_state``,
    ``iscope_get_app_state``, ``scope_get_equ_coord``,
    ``scope_get_horiz_coord``) so that :data:`event_stream.LATEST_STATE`
    stays up to date even when the Seestar is idle.

    Parameters
    ----------
    writer : asyncio.StreamWriter
        The open TCP writer for the Seestar connection.
    """
    hb_i = 0
    while not _shutdown_event.is_set():
        if hb_i % 10 == 0:        # Every 20th heartbeat
            method_name = "get_device_state"
        elif hb_i % 10 == 4:       # Every 30th heartbeat, offset by 15 heartbeats
            method_name = "iscope_get_app_state"
        elif hb_i % 3 == 1:         # Every 3rd heartbeat
            method_name = "scope_get_equ_coord"
        else:
            method_name = "scope_get_horiz_coord"
        hb_i += 1

        if writer is not None:
            heartbeat_msg = {"id": int(time.time()), "method": method_name}
            data = json.dumps(heartbeat_msg) + "\r\n"
            writer.write(data.encode())
            await writer.drain()
            if VERBOSE_LEVEL >= 2:
                print("[heartbeat] Sent:", heartbeat_msg)

        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def run():
    """
    Main event loop: connect to the Seestar and process incoming events.

    Opens a persistent TCP connection, starts a :func:`heartbeat` task,
    and reads newline-delimited JSON messages.  Each message is passed
    to :func:`event_stream.handle_event`.  Automatically reconnects on
    connection loss.
    """
    while not _shutdown_event.is_set():
        writer = None
        try:
            print(f"Connecting to {DEFAULT_IP}:{DEFAULT_PORT}...")
            reader, writer = await asyncio.open_connection(DEFAULT_IP, DEFAULT_PORT)
            print(f"Connected to {DEFAULT_IP}:{DEFAULT_PORT}")

            hb_task = asyncio.create_task(heartbeat(writer))

            while not _shutdown_event.is_set():
                try:
                    line = await asyncio.wait_for(
                        reader.readuntil(separator=b"\r\n"),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    continue

                message = line.decode().strip()
                try:
                    data = json.loads(message)

                    # Treat responses to heartbeat as events
                    if "result" in data:
                        method_name = data.get("method")
                        if method_name:
                            data["Event"] = method_name

                    handle_event(data)

                    if VERBOSE_LEVEL >= 1:
                        print("[event]", data)
                except json.JSONDecodeError:
                    if VERBOSE_LEVEL >= 1:
                        print("[non-json]", message)

        except asyncio.CancelledError:
            break

        except (asyncio.IncompleteReadError, ConnectionResetError):
            print("Connection closed by Seestar. Will reconnect in 5 sec...")

        except Exception as e:
            print(f"Unexpected error: {e}")

        try:
            hb_task.cancel()
        except Exception:
            pass

        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        if not _shutdown_event.is_set():
            await asyncio.sleep(3)


async def websocket_server():
    """
    Start a WebSocket server that broadcasts :data:`event_stream.LATEST_STATE`.

    Serves on ``ws://0.0.0.0:8765``.  Each connected client receives the
    full state dictionary once per second.  Used by the HTML dashboards
    returned by :func:`dashboard_url`.
    """
    async def handler(websocket):
        connected_clients.add(websocket)
        try:
            while not _shutdown_event.is_set():
                await asyncio.sleep(1)
                await websocket.send(json.dumps(LATEST_STATE))
        except:
            pass
        finally:
            connected_clients.remove(websocket)

    server = await websockets.serve(handler, "0.0.0.0", 8765)
    print("[websocket] Serving on ws://0.0.0.0:8765")
    while not _shutdown_event.is_set():
        await asyncio.sleep(1)
    server.close()
    await server.wait_closed()


def start_listener(with_websocket: bool = True):
    """
    Start the background event listener in a daemon thread.

    Opens a persistent TCP connection to the Seestar and continuously
    reads incoming event messages, keeping
    :data:`event_stream.LATEST_STATE` up to date.  Optionally starts a
    WebSocket server so that the bundled HTML dashboards can display
    live data.

    This function is safe to call multiple times — subsequent calls are
    a no-op if the listener is already running.

    Parameters
    ----------
    with_websocket : bool, optional
        Also start the WebSocket relay server on ``ws://0.0.0.0:8765``.
        Default is ``True``.

    See Also
    --------
    stop_listener : Stop the background listener.
    dashboard_url : Get paths to the bundled HTML dashboards.

    Examples
    --------

        >>> from seestarpy import start_listener, stop_listener
        >>> start_listener()
        [seestarpy] Starting background thread with asyncio loop.
        Connecting to 192.168.1.243:4700...
        Connected to 192.168.1.243:4700
        >>> stop_listener()

    """
    global _listener_running, _listener_thread, _shutdown_event, _loop
    if _listener_running:
        print("[seestarpy] Listener already running.")
        return

    _listener_running = True
    _shutdown_event = asyncio.Event()

    async def main():
        global _loop
        _loop = asyncio.get_running_loop()
        tasks = [asyncio.create_task(run())]
        if with_websocket:
            tasks.append(asyncio.create_task(websocket_server()))
            paths = [str(p.resolve()) for p in dashboard_url()]
            br = "\n- "
            print(f"[seestarpy] Dashboards are available:\n- {br.join(paths)}")
        await asyncio.gather(*tasks)

    def thread_entry():
        asyncio.run(main())

    print("[seestarpy] Starting background thread with asyncio loop.")
    _listener_thread = threading.Thread(target=thread_entry, daemon=True)
    _listener_thread.start()


def stop_listener():
    """
    Stop the background event listener.

    Signals the listener thread to shut down and clears internal state.
    Safe to call even if the listener is not running.

    See Also
    --------
    start_listener : Start the background listener.
    """
    global _listener_running, _listener_thread, _shutdown_event, _loop
    if not _listener_running:
        return
    print("[seestarpy] Stopping listener...")

    # Signal shutdown to all coroutines (thread-safe)
    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_shutdown_event.set)
    elif _shutdown_event is not None:
        _shutdown_event.set()

    # Wait for the thread to finish
    if _listener_thread is not None:
        _listener_thread.join(timeout=10)

    _listener_running = False
    _listener_thread = None
    _shutdown_event = None
    _loop = None


def dashboard_url():
    """
    Get file paths to the bundled HTML dashboard pages.

    These dashboards connect to the WebSocket server started by
    :func:`start_listener` and display live Seestar state.  Open the
    returned paths in a web browser.

    Returns
    -------
    list of pathlib.Path
        Paths to the ``basic.html`` and ``fancy.html`` dashboard files.

    Examples
    --------

        >>> from seestarpy.events.event_listener import dashboard_url
        >>> dashboard_url()
        [PosixPath('.../dashboards/basic.html'), PosixPath('.../dashboards/fancy.html')]

    """
    paths = [Path(__file__).parent.parent / "dashboards" / f"{which}.html"
             for which in ["basic", "fancy"]]
    return paths
