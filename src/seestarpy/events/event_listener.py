import asyncio
import json
import time

from src.seestarpy.connection import DEFAULT_IP, DEFAULT_PORT, VERBOSE_LEVEL
HEARTBEAT_INTERVAL = 10


async def heartbeat(writer):
    """Send periodic heartbeat messages to keep connection alive."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        if writer is not None:
            heartbeat_msg = {"id": int(time.time()), "method": "scope_get_equ_coord"}
            data = json.dumps(heartbeat_msg) + "\r\n"
            writer.write(data.encode())
            await writer.drain()
            if VERBOSE_LEVEL >= 2: print("[heartbeat] Sent:", heartbeat_msg)


async def run():
    """
    Watch for and print out parsed Event text

    Examples
    --------

    code-block:: python

        import asyncio
        from seestarpy.event_watcher import run
        asyncio.run(run())

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
                    if VERBOSE_LEVEL >= 1: print("[event]", data)
                except json.JSONDecodeError:
                    if VERBOSE_LEVEL >= 1: print("[non-json]", message)

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
    asyncio.run(run())
