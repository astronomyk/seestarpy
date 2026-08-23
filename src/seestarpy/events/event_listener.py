import asyncio
import json
import time
import threading

from .. import connection
from .event_stream import handle_event

HEARTBEAT_INTERVAL = 3
_listener_running = False  # Prevent multiple starts
_shutdown_event = None
_listener_thread = None
_loop = None  # asyncio event loop running in the listener thread


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
            if connection.VERBOSE_LEVEL >= 2:
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
            # Resolve the target per attempt, not once at import: this
            # module used to hold a snapshot of DEFAULT_IP taken when the
            # package was first imported, so a listener started after
            # set_default_ip() silently connected to the previous scope.
            ip, port = connection.current_ip(), connection.DEFAULT_PORT
            print(f"Connecting to {ip}:{port}...")
            reader, writer = await asyncio.open_connection(ip, port)
            print(f"Connected to {ip}:{port}")

            # Authenticate if a key is configured (firmware 7.18+).
            from ..auth import authenticate_async, KEY_PATH as _AUTH_KEY
            if _AUTH_KEY is not None:
                await authenticate_async(reader, writer)

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

                    if connection.VERBOSE_LEVEL >= 1:
                        print("[event]", data)
                except json.JSONDecodeError:
                    if connection.VERBOSE_LEVEL >= 1:
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


def start_listener():
    """
    Start the background event listener in a daemon thread.

    Opens a persistent TCP connection to the Seestar and continuously
    reads incoming event messages, keeping
    :data:`event_stream.LATEST_STATE` up to date.

    This function is safe to call multiple times — subsequent calls are
    a no-op if the listener is already running.

    The listener follows one scope, resolved from
    :func:`~seestarpy.connection.current_ip` when it connects.  For several
    scopes at once use :mod:`seestarpy.dashboard`, which runs an independent
    event connection per scope.

    .. versionchanged:: 0.7.1
       The WebSocket relay this used to start on ``ws://0.0.0.0:8765``, and
       the flag that controlled it, are gone.  Its only consumers were the
       single-scope ``basic.html`` / ``fancy.html`` pages removed in 0.7.0;
       :mod:`seestarpy.dashboard` serves its own page over HTTP and opens its
       own connections.  Read :data:`event_stream.LATEST_STATE` directly to
       feed a UI of your own.

    See Also
    --------
    stop_listener : Stop the background listener.
    dashboard_url : URL of the seestarpy web dashboard.

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
        await run()

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


def dashboard_url(port=None):
    """
    Get the URL of the seestarpy web dashboard.

    .. versionchanged:: 0.7
       The single-scope ``basic.html`` / ``fancy.html`` files this used to
       return were replaced by :mod:`seestarpy.dashboard`, a served page
       that discovers *every* Seestar on the network and gives each one a
       card with its live image and status.  Start it with
       :func:`seestarpy.dashboard.serve` (or ``python -m
       seestarpy.dashboard``) — it does not need :func:`start_listener`,
       as it runs its own per-scope event connections.

    Parameters
    ----------
    port : int, optional
        Port the dashboard is served on.  Defaults to
        :data:`seestarpy.dashboard.server.DEFAULT_PORT` (8080).

    Returns
    -------
    str
        The dashboard URL.

    Examples
    --------

        >>> from seestarpy.events.event_listener import dashboard_url
        >>> dashboard_url()
        'http://localhost:8080/'

    """
    from ..dashboard.server import DEFAULT_PORT
    return f"http://localhost:{port or DEFAULT_PORT}/"
