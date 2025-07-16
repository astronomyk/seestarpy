import asyncio
import json
import time

from .connection import DEFAULT_IP, DEFAULT_PORT
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
            print("[heartbeat] Sent:", heartbeat_msg)


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
                    print("[event]", data)
                except json.JSONDecodeError:
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


import asyncio
import json


class SeestarListener:
    """
    Create a persistent SeestarListener to track your telescope state.

    This object connects to your Seestar telescope at the given host and port,
    listens for JSON event messages, and maintains a structured state dictionary
    with live data. It runs asynchronously in the background, allowing you to
    continue running normal loops or notebook cells.

    Parameters
    ----------
    host : str, optional
        IP address of the Seestar telescope (default is "192.168.4.1").
    port : int, optional
        Port to connect to for event updates (default is 4700).

    Examples
    --------
    Basic usage to start the listener in the background:

    >>> listener = SeestarListener()
    >>> listener.start()

    Then you can run normal loops, using the ``await asyncio.sleep()`` commands:

    >>> for _ in range(5):
    ...     print("Current RA:", listener.state["position"]["ra"])
    ...     await asyncio.sleep(1)

    Print a structured summary of all current telescope state:

    >>> listener.summary()

    The latest state is always available as a dictionary:

    >>> listener.state

    Stop the listener cleanly when done:

    >>> listener.stop()
    """
    def __init__(self, host=DEFAULT_IP, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self._task = None

        self.state = {
            "position": {
                "ra": None,
                "dec": None,
                "alt": None,
                "az": None,
                "tracking": None,
            },
            "initialization": {
                "eq_mode": None,
                "dark": None,
                "focus": None,
                "three_ppa": None,
            },
            "imaging": {
                "view_state": None,
                "total_frames": 0,
                "dropped_frames": 0,
                "target_name": None,
            },
            "misc": {
                "battery": None,
                "freeMB": None,
            }
        }

    async def connect_and_listen(self):
        while True:
            try:
                print(f"Connecting to {self.host}:{self.port}")
                reader, writer = await asyncio.open_connection(self.host,
                                                               self.port)
                print(f"Connected to {self.host}:{self.port}")

                while True:
                    line = await reader.readuntil(separator=b"\r\n")
                    message = line.decode().strip()
                    try:
                        data = json.loads(message)
                        self.update_state(data)
                    except json.JSONDecodeError:
                        print("[non-json]", message)

            except (asyncio.IncompleteReadError, ConnectionResetError):
                print("Connection lost. Reconnecting in 5 sec...")
            except Exception as e:
                print(f"Unexpected error: {e}")

            await asyncio.sleep(5)

    def update_state(self, data):
        # parse different types of messages
        event = data.get("Event")

        if event == "EqCoord":
            self.state["position"]["ra"] = data.get("ra")
            self.state["position"]["dec"] = data.get("dec")
            self.state["position"]["tracking"] = data.get("tracking")
        elif event == "HorCoord":
            self.state["position"]["alt"] = data.get("alt")
            self.state["position"]["az"] = data.get("az")
        elif event == "EqMode":
            self.state["initialization"]["eq_mode"] = data.get("mode")
        elif event == "DarkLibrary":
            self.state["initialization"]["dark"] = data.get("state")
        elif event == "FocusState":
            self.state["initialization"]["focus"] = data.get("state")
        elif event == "3PPA":
            self.state["initialization"]["three_ppa"] = data.get("state")
        elif event == "View":
            self.state["imaging"]["view_state"] = data.get("state")
            self.state["imaging"]["total_frames"] = data.get("total")
            self.state["imaging"]["dropped_frames"] = data.get("dropped")
            self.state["imaging"]["target_name"] = data.get("target")
        elif event == "Battery":
            self.state["misc"]["battery"] = data.get("percent")
        elif event == "Storage":
            self.state["misc"]["freeMB"] = data.get("freeMB")

        # For debug
        print("[updated state]", self.state)


    def start(self):
        self._task = asyncio.create_task(self.connect_and_listen())
        print("SeestarListener started in background.")


    def stop(self):
        if self._task:
            self._task.cancel()
            print("SeestarListener stopped.")


    def summary(self):
        lines = []
        lines.append("=== Seestar Status Summary ===")

        pos = self.state["position"]
        lines.append(
            f"Position: RA={pos['ra']}, DEC={pos['dec']}, ALT={pos['alt']}, AZ={pos['az']}, Tracking={pos['tracking']}")

        init = self.state["initialization"]
        lines.append(
            f"Init: EQ Mode={init['eq_mode']}, Dark={init['dark']}, Focus={init['focus']}, 3PPA={init['three_ppa']}")

        img = self.state["imaging"]
        lines.append(
            f"Imaging: View State={img['view_state']}, Total Frames={img['total_frames']}, Dropped Frames={img['dropped_frames']}, Target={img['target_name']}")

        misc = self.state["misc"]
        lines.append(f"Misc: Battery={misc['battery']}%, FreeMB={misc['freeMB']}")

        summary_text = "\n".join(lines)
        print(summary_text)
        return summary_text
