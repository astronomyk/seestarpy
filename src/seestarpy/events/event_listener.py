import asyncio
import threading
import json
import time
from src.seestarpy.connection import DEFAULT_IP, DEFAULT_PORT, VERBOSE_LEVEL
from .event_stream import handle_event


HEARTBEAT_INTERVAL = 10
_listener_running = False  # Prevent multiple starts


def is_running_in_jupyter():
    try:
        from IPython import get_ipython
        return get_ipython().__class__.__name__ == "ZMQInteractiveShell"
    except Exception:
        return False


async def heartbeat(writer):
    """Send periodic heartbeat messages to keep connection alive."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        if writer is not None:
            heartbeat_msg = {"id": int(time.time()), "method": "scope_get_equ_coord"}
            data = json.dumps(heartbeat_msg) + "\r\n"
            writer.write(data.encode())
            await writer.drain()
            if VERBOSE_LEVEL >= 2:
                print("[heartbeat] Sent:", heartbeat_msg)


async def run():
    """
    Watch for and handle Seestar event messages.
    """
    while True:
        try:
            print(f"Connecting to {DEFAULT_IP}:{DEFAULT_PORT}...")
            reader, writer = await asyncio.open_connection(DEFAULT_IP, DEFAULT_PORT)
            print(f"Connected to {DEFAULT_IP}:{DEFAULT_PORT}")

            hb_task = asyncio.create_task(heartbeat(writer))

            while True:
                line = await reader.readuntil(separator=b"\r\n")
                message = line.decode().strip()
                try:
                    data = json.loads(message)
                    handle_event(data)
                    if VERBOSE_LEVEL >= 1:
                        print("[event]", data)
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


def start_listener():
    global _listener_running
    if _listener_running:
        print("[seestarpy] Listener already running.")
        return

    _listener_running = True

    def launch():
        asyncio.run(run())

    try:
        loop = asyncio.get_running_loop()
        print("[seestarpy] Using running event loop with create_task().")
        asyncio.create_task(run())
    except RuntimeError:
        print("[seestarpy] No running loop — starting background thread.")
        t = threading.Thread(target=launch, daemon=True)
        t.start()
