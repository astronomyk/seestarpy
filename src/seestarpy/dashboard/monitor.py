"""Per-Seestar monitoring: event stream + live image, one object per scope.

A :class:`ScopeMonitor` owns two long-lived TCP connections to a single
Seestar and keeps a snapshot of everything the dashboard needs to draw
one card:

- **Port 4700** — a persistent JSON-RPC connection.  Unsolicited events
  (``Stack``, ``View``, ``PiStatus``, ...) arrive on their own; a slow
  heartbeat cycle polls ``get_device_state``, ``iscope_get_app_state``
  and the two coordinate endpoints so the card is still populated when
  the scope is idle and emitting nothing.
- **Port 4800** — the binary image stream (see :mod:`seestarpy.stream`).
  Frames are decoded, stretched, downsampled and JPEG-encoded so the
  browser can show them with a plain ``<img>`` tag.

A :class:`Fleet` discovers every Seestar on the network with
:func:`seestarpy.connection.discover`, spawns one monitor per scope, and
re-scans periodically so scopes that are switched on later appear
without restarting the dashboard.

Both classes are thread-safe: :meth:`ScopeMonitor.snapshot`,
:meth:`ScopeMonitor.jpeg` and :meth:`Fleet.snapshot` may be called from
any thread (in practice, from the HTTP server's worker threads).
"""

import io
import json
import socket
import threading
import time

from .. import connection
from .. import stream as _stream
from ..status import azimuth_to_compass, pixel_scale

#: Seconds between heartbeat polls on the command connection.
HEARTBEAT_INTERVAL = 2.0

#: Shortest gap between image requests, in seconds.  A stacked image only
#: changes once per sub-exposure (10-30 s), so asking faster than this
#: buys nothing.
REQUEST_INTERVAL = 10.0

#: Gap after a request that produced no image (the scope isn't imaging).
IDLE_REQUEST_INTERVAL = 20.0

#: Multiplier applied to the last fetch's duration when pacing the next
#: one.  A stacked S30 Pro frame is ~50 MB and takes ~30 s over Wi-Fi;
#: at 1.0 the dashboard would be downloading permanently, starving the
#: scopes' own uploads.  At 2.0 it is off the air two-thirds of the time.
#: Lower it if your scopes are on a wired link.
REQUEST_BACKOFF = 2.0

#: Ack/keepalive frames to skip before giving up on an image request.
MAX_ACK_FRAMES = 10

#: Long-side length in pixels of the JPEG served to the browser.  The
#: cards are a few hundred pixels wide, so anything larger is bandwidth
#: spent on detail nobody sees.
DISPLAY_LONG_SIDE = 720

#: JPEG quality for the served frames.
JPEG_QUALITY = 82

#: Seconds of complete silence (no events, no heartbeat replies) before a
#: connection is assumed dead and rebuilt.
SOCKET_TIMEOUT = 45.0

#: Per-``recv`` timeout on the command socket.  Short so the read loop
#: keeps control and can send heartbeats on time; it is not a liveness
#: test, :data:`SOCKET_TIMEOUT` is.
RECV_POLL_TIMEOUT = 1.0

#: Seconds to wait before retrying a dropped connection.
RECONNECT_DELAY = 5.0

#: Filter-wheel positions, as labelled in the app.
_FILTER_NAMES = {0: "DARK", 1: "IRCUT", 2: "LP"}


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _require_imaging():
    """Import NumPy and Pillow, with an actionable message if missing."""
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "The dashboard needs NumPy and Pillow to decode the Seestar's "
            "image stream.  Install them with:\n"
            "    pip install 'seestarpy[dashboard]'\n"
            "or\n"
            "    pip install numpy pillow"
        ) from exc


def _block_reduce(arr, factor):
    """Average *arr* in ``factor`` x ``factor`` blocks over its first two axes.

    Used instead of plain striding because a preview frame is an
    un-debayered Bayer mosaic: striding would sample a single colour
    site and skew the whole image, while a 2x2 block mean collapses one
    Bayer quad into one luminance pixel, which is exactly what we want
    for a small monochrome preview.
    """
    import numpy as np

    if factor <= 1:
        return arr
    h, w = arr.shape[:2]
    h2, w2 = (h // factor) * factor, (w // factor) * factor
    if h2 == 0 or w2 == 0:
        return arr
    arr = arr[:h2, :w2]
    if arr.ndim == 2:
        shaped = arr.reshape(h2 // factor, factor, w2 // factor, factor)
        return shaped.mean(axis=(1, 3), dtype=np.float32)
    shaped = arr.reshape(h2 // factor, factor, w2 // factor, factor,
                         arr.shape[2])
    return shaped.mean(axis=(1, 3), dtype=np.float32)


def encode_frame(header, payload, long_side=DISPLAY_LONG_SIDE,
                 quality=JPEG_QUALITY):
    """Decode one stream frame and return display-ready JPEG bytes.

    The frame is decoded with :func:`seestarpy.stream.decode_payload`,
    reduced towards *long_side*, auto-stretched with the same midtone
    transfer function the rest of the package uses, and JPEG-encoded.

    Parameters
    ----------
    header : dict
        Parsed 34-byte frame header.
    payload : bytes
        Raw frame payload.
    long_side : int, optional
        Target length of the image's longer side, in pixels.
    quality : int, optional
        JPEG quality, 1-95.

    Returns
    -------
    tuple[bytes, tuple[int, int]]
        ``(jpeg_bytes, (width, height))`` of the *original* frame.

    Raises
    ------
    ValueError
        If the payload is an ack/keepalive or otherwise undecodable.
    """
    import numpy as np
    from PIL import Image

    # Firmware 8.46+ hands over a finished JPEG.  Re-stretching it would
    # wreck an image the firmware already tone-mapped, and decoding it to
    # an array only to re-encode would be wasted work — just resize.
    if payload[:3] == _stream._JPEG_SOI:
        img = Image.open(io.BytesIO(payload))
        img.load()
        full_w, full_h = img.size
        return _fit_and_encode(img, long_side, quality), (full_w, full_h)

    arr = _stream.decode_payload(payload, header)
    full_h, full_w = arr.shape[0], arr.shape[1]

    # Cheap integer block-reduce first (this is where the pixels are), then
    # let Pillow do the final non-integer fit.  A Bayer preview always gets
    # at least a 2x2 reduction so one quad becomes one luminance pixel.
    factor = max(1, int(max(full_h, full_w) // max(long_side, 1)))
    if arr.ndim == 2:
        factor = max(2, factor - (factor % 2))
    arr = _block_reduce(arr, factor)

    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=2)

    arr8 = _stream.auto_stretch(arr)
    # No explicit mode: Pillow infers RGB from the (H, W, 3) uint8 shape, and
    # passing it is deprecated from Pillow 13.
    return _fit_and_encode(Image.fromarray(arr8), long_side, quality), \
        (full_w, full_h)


def _fit_and_encode(img, long_side, quality):
    """Resize *img* to fit *long_side* and return JPEG bytes."""
    from PIL import Image

    if img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > long_side:
        scale = long_side / max(img.size)
        img = img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
            Image.LANCZOS,
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _num(value):
    """Return *value* if it is a real number, else ``None``.

    Guards against the firmware's habit of answering an unsupported
    query with a string or an error dict where a number is expected.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _round(value, nd):
    value = _num(value)
    return None if value is None else round(value, nd)


def _pair(result, keys):
    """Pull a coordinate pair out of a firmware reply of either shape.

    ``scope_get_equ_coord`` answers with a dict (``{"ra": .., "dec": ..}``)
    while ``scope_get_horiz_coord`` answers with a bare ``[alt, az]`` list —
    and which of the two you get has changed between firmware versions.
    Returns ``(None, None)`` for anything unrecognised.
    """
    if isinstance(result, dict):
        return _num(result.get(keys[0])), _num(result.get(keys[1]))
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        return _num(result[0]), _num(result[1])
    return None, None


# ---------------------------------------------------------------------------
# One Seestar
# ---------------------------------------------------------------------------

class ScopeMonitor:
    """Keeps one Seestar's state and latest image up to date.

    Parameters
    ----------
    sn : str
        Serial number, e.g. ``'a3497936'``.  This is the card's identity
        and survives the scope changing IP address.
    ip : str
        Current IP address.
    model : str, optional
        Product model as reported by discovery, e.g. ``'Seestar S50'``.
    dev_id : str, optional
        Short ``model_serial`` identifier, e.g. ``'s50_a3497936'``.
    port : int, optional
        Image-stream port.  :data:`seestarpy.stream.IMAGE_PORT` (4800,
        telephoto) by default; pass 4804 for the wide camera.
    """

    def __init__(self, sn, ip, model="", dev_id=None,
                 port=_stream.IMAGE_PORT):
        self.sn = sn
        self.ip = ip
        self.model = model or "Seestar"
        self.dev_id = dev_id or sn
        self.image_port = port

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []

        # Latest RPC results, keyed by method name, and latest unsolicited
        # events, keyed by event name.  Kept separate because an event and
        # a polled result can disagree and the event is the fresher of the
        # two (see _view()).
        self._rpc = {}
        self._events = {}

        self._jpeg = None
        self._frame_seq = 0
        self._frame_meta = {}
        self._frame_time = 0.0

        self._connected = False
        self._last_event_time = 0.0
        self._error = None
        self._image_error = None

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        """Start the command and image threads (idempotent)."""
        if self._threads:
            return
        self._stop.clear()
        for target, name in ((self._command_loop, "cmd"),
                             (self._image_loop, "img")):
            thread = threading.Thread(
                target=target, daemon=True,
                name=f"seestar-{self.sn}-{name}",
            )
            thread.start()
            self._threads.append(thread)

    def stop(self):
        """Signal both threads to shut down and wait briefly for them."""
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads = []

    def set_ip(self, ip):
        """Point the monitor at a new address (after DHCP moved the scope).

        The running sockets are left to fail on their own; the reconnect
        loops pick up the new address on their next attempt.
        """
        with self._lock:
            if ip == self.ip:
                return
            self.ip = ip

    # -- command connection (port 4700) ------------------------------------

    _HEARTBEAT_CYCLE = [
        "get_device_state",
        "scope_get_equ_coord",
        "scope_get_horiz_coord",
        "iscope_get_app_state",
        "scope_get_equ_coord",
        "scope_get_horiz_coord",
        "iscope_get_app_state",
        "get_wheel_position",
    ]

    def _command_loop(self):
        """Hold a JSON-RPC connection open, polling and reading events."""
        while not self._stop.is_set():
            sock = None
            try:
                sock = self._connect_command()
                self._set_connected(True)
                self._read_events(sock)
            except Exception as exc:
                self._set_connected(False, exc)
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if not self._stop.is_set():
                self._stop.wait(RECONNECT_DELAY)
        self._set_connected(False)

    def _connect_command(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((self.ip, connection.DEFAULT_PORT))
        # Firmware 7.18+ wants a signed challenge before it will talk.
        from .. import auth
        if auth.KEY_PATH is not None:
            auth.authenticate(sock)
        # Short recv timeout so the loop below keeps control and can send
        # heartbeats on schedule; liveness is tracked separately.
        sock.settimeout(RECV_POLL_TIMEOUT)
        return sock

    def _read_events(self, sock):
        """Read ``\\r\\n``-delimited JSON until the socket dies."""
        buf = ""
        next_beat = 0.0
        beat = 0
        last_rx = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_beat:
                method = self._HEARTBEAT_CYCLE[beat % len(self._HEARTBEAT_CYCLE)]
                beat += 1
                next_beat = now + HEARTBEAT_INTERVAL
                sock.sendall(
                    (json.dumps({"id": int(time.time()), "method": method})
                     + "\r\n").encode()
                )

            try:
                chunk = sock.recv(8192)
            except socket.timeout:
                # Expected: an idle scope emits no events between heartbeat
                # replies.  Only a long silence means it is actually gone —
                # blocking here until SOCKET_TIMEOUT instead would stop the
                # heartbeats and make every idle scope flap.
                if time.monotonic() - last_rx > SOCKET_TIMEOUT:
                    raise ConnectionError(
                        f"silent for {SOCKET_TIMEOUT:.0f}s despite heartbeats")
                continue
            if not chunk:
                raise ConnectionError("Seestar closed the connection")

            last_rx = time.monotonic()
            buf += chunk.decode("utf-8", "replace")
            while "\r\n" in buf:
                line, buf = buf.split("\r\n", 1)
                if line.strip():
                    self._handle_message(line)

    def _handle_message(self, line):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return

        with self._lock:
            self._last_event_time = time.time()
            event = data.get("Event")
            if event:
                self._events[event] = data
            method = data.get("method")
            if method and "result" in data:
                self._rpc[method] = data.get("result")

    def _set_connected(self, ok, error=None):
        with self._lock:
            self._connected = bool(ok)
            self._error = None if ok else (str(error) if error else self._error)

    # -- image connection (port 4800) --------------------------------------

    def _image_loop(self):
        """Poll the image socket, keeping the latest JPEG fresh.

        Deliberately request/response rather than ``begin_streaming``:
        the continuous stream pushes every preview frame at full size —
        16 MB apiece on an S30 Pro — which saturates the Wi-Fi for no
        benefit when the card only redraws every few seconds.  Asking
        for one frame at a time costs one transfer per refresh, and the
        pacing below keeps even that off the air most of the time.
        """
        try:
            _require_imaging()
        except ImportError as exc:
            # _image_error, not _error: the command connection clears _error
            # on every successful reconnect, which would wipe this.
            with self._lock:
                self._image_error = str(exc)
            return

        while not self._stop.is_set():
            sock = None
            try:
                sock = _stream._make_socket(self.ip, self.image_port,
                                            timeout=10)
                sock.settimeout(SOCKET_TIMEOUT)
                self._poll_frames(sock)
            except Exception as exc:
                # Image failures are non-fatal and common — the scope drops
                # the stream while slewing, and some firmware refuses a
                # second image client while the phone app holds one.  Keep
                # the last frame, record why, and reconnect.
                with self._lock:
                    self._image_error = f"{type(exc).__name__}: {exc}"
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if not self._stop.is_set():
                self._stop.wait(RECONNECT_DELAY)

    def _poll_frames(self, sock):
        """Fetch one frame at a time until the socket dies or we stop."""
        while not self._stop.is_set():
            started = time.monotonic()

            # The stack is the image worth showing.  When there isn't one
            # (the scope is framing, focusing or idle) the request is
            # answered with an ack and we fall back to the live preview.
            got = self._request_frame(sock, "get_stacked_img")
            if not got:
                got = self._request_frame(sock, "get_current_img")

            # Adaptive pacing: a full-size frame takes 10-30 s to cross a
            # Wi-Fi link, and asking again immediately would mean never
            # being off the air.  Wait at least as long as the fetch took,
            # so a slow scope self-throttles and a fast one stays snappy.
            elapsed = time.monotonic() - started
            wait = max(REQUEST_INTERVAL, elapsed * REQUEST_BACKOFF)
            if not got:
                wait = max(wait, IDLE_REQUEST_INTERVAL)
            if self._stop.wait(wait):
                return

    def _request_frame(self, sock, method):
        """Ask for one frame and store it.  ``True`` if an image arrived.

        Zero-dimension ack frames are skipped: the firmware answers a
        ``get_stacked_img`` with one when no stack exists yet, which is
        how "not stacking" is detected.
        """
        _stream._send_json(sock, method)
        for _ in range(MAX_ACK_FRAMES):
            header, payload = _stream._read_frame(sock)
            # Must not test width/height here: a firmware 8.46+ JPEG frame
            # reports 0x0 and is still a full image.  Treating it as an ack
            # left the loop waiting for a frame that never came, until the
            # scope dropped the connection.
            if not _stream.is_image_frame(header):
                continue  # ack / keepalive

            # Classify by what actually arrived, not by what was asked
            # for, so a late frame from the previous request is still
            # labelled correctly.
            stacked = _stream.is_stacked_frame(header)
            try:
                jpeg, (width, height) = encode_frame(header, payload)
            except (ValueError, OSError):
                continue

            with self._lock:
                self._jpeg = jpeg
                self._frame_seq += 1
                self._frame_time = time.time()
                # Only a delivered frame clears the error.  Clearing it on
                # reconnect instead would hide a scope that fails on every
                # attempt, since it reconnects between every failure.
                self._image_error = None
                self._frame_meta = {
                    "kind": "stacked" if stacked else "live",
                    "width": width,
                    "height": height,
                    "frame_id": header.get("image_id"),
                }
            return True
        return False

    # -- readers -----------------------------------------------------------

    def jpeg(self):
        """Return ``(jpeg_bytes, seq)`` for the latest frame, or ``(None, 0)``."""
        with self._lock:
            return self._jpeg, self._frame_seq

    def _view(self):
        """Merge the polled ``View`` block with the fresher ``View`` event."""
        view = dict((self._rpc.get("iscope_get_app_state") or {}).get("View", {}))
        event = self._events.get("View")
        if event:
            view.update({k: v for k, v in event.items()
                         if k not in ("Event", "Timestamp", "route")})
        return view

    def _stack(self, view):
        """Merge the ``Stack`` sub-block with the fresher ``Stack`` event."""
        stack = dict(view.get("Stack", {}) or {})
        event = self._events.get("Stack")
        if event:
            stack.update({k: v for k, v in event.items()
                          if k not in ("Event", "Timestamp", "route")})
        return stack

    def snapshot(self):
        """Return the full card payload for this scope as a plain dict.

        Every field is JSON-serialisable and every value that could not
        be read is ``None``, so the front end can render a dash without
        having to know which firmware version produced the data.
        """
        with self._lock:
            device = self._rpc.get("get_device_state") or {}
            view = self._view()
            stack = self._stack(view)
            events = dict(self._events)
            connected = self._connected
            error = self._error
            image_error = self._image_error
            frame_meta = dict(self._frame_meta)
            frame_seq = self._frame_seq
            frame_time = self._frame_time
            last_event = self._last_event_time
            equ = self._rpc.get("scope_get_equ_coord") or {}
            horiz = self._rpc.get("scope_get_horiz_coord") or {}
            wheel = self._rpc.get("get_wheel_position")
            ip = self.ip

        setting = device.get("setting", {}) or {}
        mount = device.get("mount", {}) or {}
        pi = device.get("pi_status", {}) or {}
        pi.update({k: v for k, v in (events.get("PiStatus") or {}).items()
                   if k not in ("Event", "Timestamp", "route")})
        station = device.get("station", {}) or {}
        dev = device.get("device", {}) or {}
        volumes = (device.get("storage", {}) or {}).get("storage_volume") or [{}]

        # Exposure: the live View block is authoritative while a session is
        # running; fall back to the configured stacking exposure when idle.
        exp_ms = _num((stack.get("Exposure", {}) or {}).get("exp_ms"))
        if exp_ms is None:
            exp_ms = _num((setting.get("exp_ms", {}) or {}).get("stack_l"))
        exp_s = None if exp_ms is None else exp_ms / 1000.0

        stacked = _num(stack.get("stacked_frame"))
        dropped = _num(stack.get("dropped_frame"))
        total = None
        if stacked is not None and dropped is not None:
            total = stacked + dropped
        dropped_pct = None
        if total:
            dropped_pct = 100.0 * dropped / total

        stack_time_s = None
        if stacked is not None and exp_s is not None:
            stack_time_s = stacked * exp_s

        # Wi-Fi vs wired: the station block reports the address of the Wi-Fi
        # radio.  If we are talking to the scope on a different address, the
        # traffic must be crossing the USB-C Ethernet gadget instead.
        station_ip = station.get("ip")
        if not station_ip:
            link = None
        elif station_ip == ip:
            link = "wifi"
        else:
            link = "lan"

        if isinstance(wheel, dict):
            wheel = wheel.get("position")
        wheel_pos = _num(wheel)
        if wheel_pos is None:
            # No wheel reading yet — lp_filter still tells us IRCUT vs LP.
            lp = view.get("lp_filter")
            filter_name = None if lp is None else ("LP" if lp else "IRCUT")
        else:
            filter_name = _FILTER_NAMES.get(int(wheel_pos), str(wheel_pos))

        dither = setting.get("stack_dither") or {}
        focal_mm = _num(dev.get("focal_len"))
        if dither.get("enable") and focal_mm:
            # pixel_scale() would go and ask the device when it isn't given a
            # focal length — snapshot() runs once a second per connected
            # browser, so it must never touch the network.
            scale = pixel_scale(focal_mm)
            dither_txt = (f"{dither.get('pix', 0) * scale / 60.0:.1f}' "
                          f"/{dither.get('interval', '?')} sub")
        elif dither.get("enable"):
            dither_txt = f"{dither.get('pix', '?')} px /{dither.get('interval', '?')} sub"
        elif dither:
            dither_txt = "off"
        else:
            dither_txt = None

        target_ra_dec = view.get("target_ra_dec") or []
        alt, az = _pair(horiz, ("alt", "az"))
        ra, dec = _pair(equ, ("ra", "dec"))

        free_mb = _num((volumes[0] or {}).get("free_mb"))
        total_mb = _num((volumes[0] or {}).get("total_mb"))

        return {
            # identity
            "sn": self.sn,
            "dev_id": self.dev_id,
            "model": dev.get("product_model") or self.model,
            "ip": ip,
            "link": link,
            "firmware": dev.get("firmware_ver_string"),

            # health
            "connected": connected,
            "error": error,
            "age_s": None if not last_event else round(time.time() - last_event, 1),

            # image
            "frame_seq": frame_seq,
            "frame_kind": frame_meta.get("kind"),
            "frame_width": frame_meta.get("width"),
            "frame_height": frame_meta.get("height"),
            "frame_age_s": (None if not frame_time
                            else round(time.time() - frame_time, 1)),
            "image_error": image_error,
            # Firmware 8.46+ only; earlier firmware has no preview block
            # and always sends Raw.
            "transfer_mode": (setting.get("preview") or {}).get(
                "image_transfer_mode", "Raw"),

            # imaging block
            "exp_s": _round(exp_s, 2),
            "gain": _num(view.get("gain")),
            "stacked_frames": stacked,
            "dropped_frames": dropped,
            "dropped_pct": _round(dropped_pct, 1),
            "stack_time_s": _round(stack_time_s, 0),
            "filter": filter_name,
            "dither": dither_txt,

            # pointing block
            "target": view.get("target_name"),
            "target_ra": _round(target_ra_dec[0] if len(target_ra_dec) > 0 else None, 4),
            "target_dec": _round(target_ra_dec[1] if len(target_ra_dec) > 1 else None, 4),
            "ra": _round(ra, 4),
            "dec": _round(dec, 4),
            "alt": _round(alt, 1),
            "az": _round(az, 1),
            "compass": None if az is None else azimuth_to_compass(az),
            "view_state": view.get("state"),
            "view_stage": view.get("stage"),
            "view_mode": view.get("mode"),
            "view_error": view.get("error") or stack.get("error"),

            # housekeeping block
            "equ_mode": mount.get("equ_mode"),
            "tracking": mount.get("tracking"),
            "parked": mount.get("close"),
            "battery": _num(pi.get("battery_capacity")),
            "charging": pi.get("charge_online"),
            "temp_c": _round(pi.get("temp"), 1),
            "free_gb": None if free_mb is None else round(free_mb / 1024.0, 1),
            "total_gb": None if total_mb is None else round(total_mb / 1024.0, 1),
        }


# ---------------------------------------------------------------------------
# All the Seestars on the network
# ---------------------------------------------------------------------------

class Fleet:
    """Discovers Seestars and keeps one :class:`ScopeMonitor` per scope.

    Parameters
    ----------
    rescan_interval : float, optional
        Seconds between UDP discovery sweeps.  Scopes powered on after
        the dashboard started show up within one interval; scopes that
        move to a new address are re-pointed at it.  Default 60.
    port : int, optional
        Image-stream port passed to every monitor.
    """

    def __init__(self, rescan_interval=60.0, port=_stream.IMAGE_PORT):
        self.rescan_interval = rescan_interval
        self.image_port = port
        self._monitors = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._last_scan = None

    def start(self):
        """Run one discovery sweep, then keep re-scanning in the background."""
        if self._thread is not None:
            return
        self._stop.clear()
        self.scan(quiet=False)
        self._thread = threading.Thread(target=self._rescan_loop, daemon=True,
                                        name="seestar-fleet-scan")
        self._thread.start()

    def stop(self):
        """Stop rescanning and shut every monitor down."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        with self._lock:
            monitors = list(self._monitors.values())
            self._monitors.clear()
        for monitor in monitors:
            monitor.stop()

    def _rescan_loop(self):
        while not self._stop.wait(self.rescan_interval):
            try:
                self.scan(quiet=True)
            except Exception as exc:  # pragma: no cover - network dependent
                print(f"[dashboard] discovery sweep failed: {exc}")

    def scan(self, quiet=True):
        """Run one UDP discovery sweep and reconcile the monitor set.

        New scopes get a monitor and start streaming immediately;
        already-known scopes that answered from a new address are
        re-pointed at it.  Scopes that did *not* answer are left alone —
        their monitor's own connection state is a better liveness signal
        than one missed broadcast reply.
        """
        connection.discover(quiet=quiet)
        self._last_scan = time.time()

        started = []
        # Snapshot the dict: another thread calling discover() while we
        # iterate would otherwise raise "changed size during iteration".
        discovered = list(connection.DISCOVERED.items())
        with self._lock:
            for sn, record in discovered:
                monitor = self._monitors.get(sn)
                if monitor is None:
                    monitor = ScopeMonitor(
                        sn=sn,
                        ip=record["ip"],
                        model=record.get("model", ""),
                        dev_id=record.get("dev_id"),
                        port=self.image_port,
                    )
                    self._monitors[sn] = monitor
                    started.append(monitor)
                else:
                    monitor.set_ip(record["ip"])

        for monitor in started:
            if not quiet:
                print(f"[dashboard] monitoring {monitor.model} "
                      f"{monitor.sn} at {monitor.ip}")
            monitor.start()
        return started

    def get(self, sn):
        """Return the monitor for serial number *sn*, or ``None``."""
        with self._lock:
            return self._monitors.get(sn)

    def snapshot(self):
        """Return ``{"scopes": [...], "scanned_at": float}`` for the whole fleet.

        Cards are ordered by serial number so a scope keeps its position
        in the grid across reloads and rescans.
        """
        with self._lock:
            monitors = [self._monitors[sn] for sn in sorted(self._monitors)]
        return {
            "scopes": [monitor.snapshot() for monitor in monitors],
            "scanned_at": self._last_scan,
            "server_time": time.time(),
        }
