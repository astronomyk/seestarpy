import asyncio
import json
import time
import websockets
import threading
from pathlib import Path

from src.seestarpy.connection import DEFAULT_IP, DEFAULT_PORT, VERBOSE_LEVEL
from .event_stream import handle_event, LATEST_STATE

HEARTBEAT_INTERVAL = 10
_listener_running = False  # Prevent multiple starts
_shutdown_event = None
_listener_thread = None

connected_clients = set()

async def heartbeat(writer):
    """Send periodic heartbeat messages to keep connection alive."""
    while not _shutdown_event.is_set():
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
    # This is not a graceful way to shut down the
    while not _shutdown_event.is_set():
        try:
            print(f"Connecting to {DEFAULT_IP}:{DEFAULT_PORT}...")
            reader, writer = await asyncio.open_connection(DEFAULT_IP, DEFAULT_PORT)
            print(f"Connected to {DEFAULT_IP}:{DEFAULT_PORT}")

            hb_task = asyncio.create_task(heartbeat(writer))

            while not _shutdown_event.is_set():
                line = await reader.readuntil(separator=b"\r\n")
                message = line.decode().strip()
                try:
                    data = json.loads(message)

                    # Treat responses to heartbeat as events
                    if "method" in data and data[
                        "method"] == "scope_get_equ_coord":
                        event_data = {
                            "Event": "Heartbeat",
                            "state": "update",
                            "Timestamp": data.get("Timestamp"),
                            "ra": data["result"]["ra"],
                            "dec": data["result"]["dec"]
                        }
                        handle_event(event_data)

                    else:
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

async def websocket_server():
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
    await server.wait_closed()

def start_listener(with_websocket: bool = False):
    global _listener_running, _listener_thread, _shutdown_event
    if _listener_running:
        print("[seestarpy] Listener already running.")
        return

    _listener_running = True
    _shutdown_event = asyncio.Event()

    async def main():
        tasks = [asyncio.create_task(run())]
        if with_websocket:
            tasks.append(asyncio.create_task(websocket_server()))
        await asyncio.gather(*tasks)

    def thread_entry():
        asyncio.run(main())

    print("[seestarpy] Starting background thread with asyncio loop.")
    _listener_thread = threading.Thread(target=thread_entry, daemon=True)
    _listener_thread.start()

def stop_listener():
    global _listener_running, _listener_thread, _shutdown_event
    if not _listener_running:
        return
    print("[seestarpy] Stopping listener...")

    # Dirty, dirty way to shut down the thread, but it works. Force an exception
    _shutdown_event = None
    _listener_running = False
    _listener_thread = None


def dashboard_url(which="basic"):
    """
    Open the basic dashboard HTML file in the default system browser.

    Parameters
    ----------
    which : str
        ["basic"]
    """
    path = Path(__file__).parent.parent / "dashboards" / f"{which}.html"
    return f"file://{path.resolve()}"
