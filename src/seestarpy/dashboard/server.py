"""The dashboard's HTTP server.

Serves a single page that draws one card per Seestar, plus the two
endpoints that keep it live:

===========================  =============================================
``GET /``                    the dashboard page (and its CSS / JS)
``GET /api/scopes``          one JSON snapshot of the whole fleet
``GET /api/events``          the same snapshot pushed once a second as a
                             Server-Sent Events stream
``GET /api/image/<sn>``      the latest JPEG frame from one Seestar
===========================  =============================================

Server-Sent Events are used rather than WebSockets because the browser
speaks them natively (``new EventSource(...)``), they reconnect on their
own, and they need nothing on the Python side beyond an HTTP response
that is never closed — which keeps the whole dashboard dependency-free
apart from the image decoding.
"""

import json
import mimetypes
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .monitor import Fleet

#: Directory holding index.html and its assets.
STATIC_DIR = Path(__file__).parent / "static"

#: Seconds between Server-Sent Event pushes.
PUSH_INTERVAL = 1.0

#: Default TCP port for the dashboard.
DEFAULT_PORT = 8080


def _local_ip():
    """Best-guess LAN address of this machine, for the printed banner."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class _Handler(BaseHTTPRequestHandler):
    """Routes requests to the static files, the JSON API and the SSE feed."""

    protocol_version = "HTTP/1.1"

    # Injected by DashboardServer before the server starts.
    fleet = None
    verbose = False

    # -- plumbing ----------------------------------------------------------

    def log_message(self, fmt, *args):
        """Silence the default per-request stderr logging unless asked for."""
        if self.verbose:
            super().log_message(fmt, *args)

    def _send(self, body, content_type, status=200, extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, status=200):
        self._send(json.dumps(payload), "application/json", status,
                   {"Cache-Control": "no-store"})

    # -- routing -----------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._serve_static("index.html")
            elif path == "/api/scopes":
                self._send_json(self.fleet.snapshot())
            elif path == "/api/events":
                self._serve_events()
            elif path.startswith("/api/image/"):
                self._serve_image(path[len("/api/image/"):])
            elif "/" not in path[1:] and path != "/":
                self._serve_static(path[1:])
            else:
                self._send_json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            # The browser navigated away mid-response; nothing to do.
            pass

    def _serve_static(self, name):
        target = (STATIC_DIR / name).resolve()
        # Reject anything that escaped the static directory (../ and friends).
        if not str(target).startswith(str(STATIC_DIR.resolve())) \
                or not target.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "text/plain"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self._send(target.read_bytes(), content_type,
                   extra_headers={"Cache-Control": "no-cache"})

    def _serve_image(self, sn):
        monitor = self.fleet.get(sn)
        if monitor is None:
            self._send_json({"error": f"unknown Seestar {sn!r}"}, 404)
            return
        jpeg, _seq = monitor.jpeg()
        if jpeg is None:
            # 204 rather than 404: the scope is known and fine, it just has
            # not delivered a decodable frame yet.
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._send(jpeg, "image/jpeg",
                   extra_headers={"Cache-Control": "no-store"})

    def _serve_events(self):
        """Hold the connection open and push a fleet snapshot every second."""
        # The body has no length and never ends, so the connection is not
        # reusable — say so, and stop the handler trying to read another
        # request off the socket once the client goes away.
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                payload = json.dumps(self.fleet.snapshot())
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(PUSH_INTERVAL)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client closed the EventSource


class DashboardServer:
    """Owns a :class:`~seestarpy.dashboard.monitor.Fleet` and its HTTP server.

    Most users want the module-level :func:`serve` instead; use this
    class directly when you need to start the dashboard from inside
    another program and shut it down again.

    Parameters
    ----------
    host : str, optional
        Interface to bind.  Defaults to ``"127.0.0.1"`` — see *lan*.
        Setting this explicitly overrides *lan*.
    port : int, optional
        TCP port.  Default :data:`DEFAULT_PORT` (8080).
    rescan_interval : float, optional
        Seconds between discovery sweeps.  Default 60.
    image_port : int, optional
        Seestar image-stream port: 4800 (telephoto, default) or 4804
        (wide camera).
    verbose : bool, optional
        Log every HTTP request to stderr.  Default ``False``.
    lan : bool, optional
        Bind ``0.0.0.0`` instead of loopback, making the dashboard
        reachable from the rest of the network — a phone, a tablet, the
        laptop in the warm room.  Default ``False``, because the
        dashboard has **no authentication** and should not appear on the
        LAN unless you meant it to.

    Examples
    --------
    ::

        >>> from seestarpy.dashboard import DashboardServer
        >>> server = DashboardServer(port=8080)
        >>> server.start()
        >>> # ... later ...
        >>> server.stop()
    """

    def __init__(self, host=None, port=DEFAULT_PORT, rescan_interval=60.0,
                 image_port=None, verbose=False, lan=False):
        from .. import stream as _stream

        # Loopback unless explicitly opened up: the dashboard has no
        # authentication, so it should not appear on the LAN by accident.
        if host is None:
            host = "0.0.0.0" if lan else "127.0.0.1"
        self.host = host
        self.port = port
        self.verbose = verbose
        self.fleet = Fleet(rescan_interval=rescan_interval,
                           port=image_port or _stream.IMAGE_PORT)
        self._httpd = None
        self._thread = None

    @property
    def url(self):
        """The dashboard's URL, using a LAN address when bound to 0.0.0.0."""
        host = _local_ip() if self.host in ("0.0.0.0", "") else self.host
        return f"http://{host}:{self.port}/"

    def start(self):
        """Discover the scopes and start serving in a background thread."""
        if self._httpd is not None:
            return self

        self.fleet.start()

        handler = type("_BoundHandler", (_Handler,),
                       {"fleet": self.fleet, "verbose": self.verbose})
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True, name="seestar-dashboard")
        self._thread.start()
        return self

    def stop(self):
        """Stop the HTTP server and every scope monitor."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        self.fleet.stop()


def serve(host=None, port=DEFAULT_PORT, open_browser=True,
          rescan_interval=60.0, image_port=None, verbose=False,
          block=True, lan=False):
    """Start the Seestar dashboard.

    Discovers every Seestar on the local network, opens a live image
    stream and an event connection to each one, and serves a page that
    draws one card per scope — the current stacked image (or the live
    preview when the scope isn't stacking) with its status alongside.

    Scopes powered on after the dashboard started are picked up by the
    next discovery sweep and their card appears on its own.

    Parameters
    ----------
    host : str, optional
        Interface to bind.  Defaults to ``"127.0.0.1"`` (this machine
        only); see *lan*.  Setting this explicitly overrides *lan*.
    port : int, optional
        TCP port to serve on.  Default 8080.
    open_browser : bool, optional
        Open the dashboard in the default browser.  Default ``True``.
    rescan_interval : float, optional
        Seconds between discovery sweeps.  Default 60.
    image_port : int, optional
        Seestar image-stream port: 4800 (telephoto, the default) or
        4804 for the wide camera.
    verbose : bool, optional
        Log HTTP requests.  Default ``False``.
    block : bool, optional
        Block until interrupted with Ctrl-C (default).  Pass ``False``
        to keep control and shut down later via the returned object.
    lan : bool, optional
        Bind ``0.0.0.0`` so the dashboard is reachable from the rest of
        the network.  Default ``False``.  The dashboard has **no
        authentication**, so only open it up on a network you trust — or
        reach it over a VPN such as Tailscale, which needs no LAN
        binding at all beyond the tunnel interface.

    Returns
    -------
    DashboardServer
        The running server.  Call ``.stop()`` on it when *block* is
        ``False``.

    Examples
    --------
    From the shell::

        python -m seestarpy.dashboard

    From Python::

        >>> from seestarpy import dashboard
        >>> dashboard.serve()                    # blocks until Ctrl-C
        >>> server = dashboard.serve(block=False)
        >>> server.stop()
    """
    server = DashboardServer(host=host, port=port,
                             rescan_interval=rescan_interval,
                             image_port=image_port, verbose=verbose,
                             lan=lan).start()

    count = len(server.fleet.snapshot()["scopes"])
    print(f"[dashboard] serving {count} Seestar(s) at {server.url}")
    if not count:
        print("[dashboard] no Seestars answered yet — the page will fill in "
              "as they are found")

    if open_browser:
        webbrowser.open(server.url)

    if block:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[dashboard] shutting down...")
            server.stop()
    return server
