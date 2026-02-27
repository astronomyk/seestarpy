"""Live image streaming from the Seestar's binary socket protocol.

The Seestar exposes two independent image streams over raw TCP:

- **Port 4800** — Telephoto camera (stacked deep-sky images)
- **Port 4804** — Wide-angle camera

Each stream uses a custom binary framing protocol: a 34-byte header
followed by an image payload.  The payload is a streaming ZIP archive
containing deflate-compressed raw pixel data (16-bit RGB, 48 bpp).
The connection is kept alive with a JSON-RPC ``test_connection``
heartbeat every 4 seconds.

.. note:: Reverse-engineered from the Seestar Android app v3.0.2
   (decompiled with JADX) and confirmed via live capture on
   2026-02-27.

Quick start
-----------

Grab and save (uses auto-discovered IP)::

    >>> from seestarpy import stream
    >>> stream.get_live_image(filename="latest.png")

The saved PNG is auto-stretched to reveal faint nebulosity.

One-shot grab (raw data)::

    >>> header, payload = stream.get_live_image()
    >>> pixels = stream.decode_payload(payload, header)
    >>> pixels.shape   # (height, width, 3) uint16
    (3840, 2160, 3)

Save as FITS::

    >>> stream.get_live_image(filename="latest.fits")

Live display (blocks until window closed)::

    >>> stream.start_stream(with_matplotlib=True)

Continuous streaming with custom callback::

    >>> def on_frame(header, data):
    ...     print(f"Frame {header['image_id']}: {header['width']}x{header['height']}")
    >>> session = stream.start_stream(on_image=on_frame)
    >>> # ... later ...
    >>> stream.stop_stream(session)

RTSP video URL (for use with ffplay / OpenCV)::

    >>> stream.build_rtsp_url()
    'rtsp://192.168.1.246:4554/stream'
"""

import json
import os
import socket
import struct
import threading
import time
import zlib

from .connection import DEFAULT_IP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMAGE_PORT = 4800
"""Default port for the telephoto camera image stream."""

IMAGE_PORT_WIDE = 4804
"""Port for the wide-angle camera image stream."""

RTSP_PORT = 4554
"""Default RTSP port for the telephoto live video feed."""

RTSP_PORT_WIDE = 4555
"""RTSP port for the wide-angle live video feed."""

HEADER_SIZE = 34
"""Size of the binary frame header in bytes."""

MAGIC_NUMBER = 0x03C3
"""Magic number (963) that marks the start of every image frame."""

HEARTBEAT_INTERVAL = 4
"""Seconds between ``test_connection`` heartbeats (matches the app)."""

_RECV_BUF = 65536
"""Socket receive buffer size (64 KB, matches the app's setting)."""

# Image-type constants from the header's ``img_type`` field.
IMG_TYPE_PREVIEW = 1
"""Single unstacked preview frame."""

IMG_TYPE_STACKED = 5
"""Progressively stacked deep-sky image."""

_ZIP_LOCAL_SIG = b'PK\x03\x04'
"""ZIP local-file-header signature used to locate the compressed data."""


# ---------------------------------------------------------------------------
# Payload decoding
# ---------------------------------------------------------------------------

def decode_payload(payload, header):
    """Decode a raw frame payload into a NumPy pixel array.

    Handles both payload formats the Seestar sends:

    - **Stacked frames** (img_type=5, data_type=3): ZIP-compressed
      16-bit RGB → ``(H, W, 3)`` uint16.
    - **Preview frames** (img_type=1, data_type=2): Raw (uncompressed)
      16-bit Bayer → ``(H, W)`` uint16.

    Parameters
    ----------
    payload : bytes
        Raw payload bytes from :func:`get_live_image` or the streaming
        callback.
    header : dict
        Parsed frame header (from :func:`parse_header`), used for
        *width* and *height*.

    Returns
    -------
    numpy.ndarray
        ``(height, width, 3)`` uint16 for stacked frames, or
        ``(height, width)`` uint16 for preview (Bayer) frames.

    Raises
    ------
    ValueError
        If the payload cannot be decoded or dimensions don't match.
    ImportError
        If NumPy is not installed.
    """
    import numpy as np

    w = header['width']
    h = header['height']

    if w == 0 or h == 0:
        raise ValueError("Zero-dimension frame (ack/keepalive)")

    # Stacked frames are ZIP-compressed RGB
    if _ZIP_LOCAL_SIG in payload:
        raw = _decompress_payload(payload)
        expected = h * w * 3 * 2
        if len(raw) != expected:
            raise ValueError(
                f"Decompressed size {len(raw)} != expected {expected} "
                f"({w}x{h}x3x2)"
            )
        return np.frombuffer(raw, dtype=np.uint16).reshape((h, w, 3))

    # Preview frames are raw 16-bit single-channel (Bayer)
    expected_bayer = h * w * 2
    if len(payload) == expected_bayer:
        return np.frombuffer(payload, dtype=np.uint16).reshape((h, w))

    raise ValueError(
        f"Unknown payload format: {len(payload)} bytes for "
        f"{w}x{h} (expected {h * w * 3 * 2} RGB or {expected_bayer} Bayer)"
    )


def save_image(payload, header, path, stretch=True):
    """Decode a frame payload and save it as an image file.

    For ``.fits`` files, the full 16-bit RGB data is saved as a FITS
    image (requires ``astropy``).  For all other formats (``.png``,
    ``.jpg``, ``.tiff``, ...) the data is auto-stretched to reveal
    faint nebulosity and saved as 8-bit via Pillow.

    Parameters
    ----------
    payload : bytes
        Raw payload bytes.
    header : dict
        Parsed frame header.
    path : str
        Output file path.  The extension determines the format.
        Use ``.fits`` to save lossless 16-bit data.
    stretch : bool, optional
        Apply an aggressive auto-stretch to bring out faint detail
        (default ``True``).  Set to ``False`` for a simple linear
        16-to-8-bit scale.  Ignored for FITS output.

    Raises
    ------
    ImportError
        If required libraries are not installed (NumPy always; Pillow
        for image formats; astropy for FITS).
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in ('.fits', '.fit'):
        _save_fits(payload, header, path)
    else:
        _save_image_pil(payload, header, path, stretch)


def _save_fits(payload, header, path):
    """Save the full 16-bit RGB data as a FITS file."""
    import numpy as np
    from astropy.io import fits

    arr = decode_payload(payload, header)
    # FITS convention: (channels, height, width)
    fits_data = np.moveaxis(arr, 2, 0)
    hdu = fits.PrimaryHDU(data=fits_data)
    hdu.header['BITPIX'] = 16
    hdu.header['IMGTYPE'] = header['img_type']
    hdu.header['IMAGEID'] = header['image_id']
    hdu.header['HFD'] = header['hfd']
    hdu.writeto(path, overwrite=True)


def _save_image_pil(payload, header, path, stretch):
    """Save as a Pillow-supported format (PNG, JPEG, TIFF, ...)."""
    import numpy as np
    from PIL import Image

    arr = decode_payload(payload, header)

    if arr.ndim == 2:
        # Single-channel Bayer → stack to RGB for consistent processing
        arr = np.stack([arr, arr, arr], axis=2)

    if stretch:
        arr8 = _auto_stretch(arr)
    else:
        arr8 = (arr >> 8).astype(np.uint8)

    img = Image.fromarray(arr8, 'RGB')
    img.save(path)


def _auto_stretch(arr):
    """Apply an aggressive midtone stretch to reveal faint nebulosity.

    Uses the Midtone Transfer Function (MTF) from PixInsight:

    .. math::

        \\text{MTF}(x, m) = \\frac{(m - 1)\\,x}{(2m - 1)\\,x - m}

    where *m* is the midtone balance (lower = more aggressive).
    Black and white points are set from percentiles so the stretch
    adapts automatically to whatever the telescope is imaging.

    Parameters
    ----------
    arr : numpy.ndarray
        ``(H, W, 3)`` uint16 array.

    Returns
    -------
    numpy.ndarray
        ``(H, W, 3)`` uint8 array, stretched.
    """
    import numpy as np

    # Work in float32 for the nonlinear curve
    img = arr.astype(np.float32)

    # Per-channel percentile clipping
    black = np.percentile(img, 0.5, axis=(0, 1), keepdims=True)
    white = np.percentile(img, 99.95, axis=(0, 1), keepdims=True)

    # Normalise to 0-1
    img = (img - black) / (white - black + 1e-6)
    np.clip(img, 0.0, 1.0, out=img)

    # Midtone Transfer Function — m=0.15 is aggressive but keeps
    # star colours intact.  MTF(x,m) = (m-1)*x / ((2m-1)*x - m)
    m = 0.15
    img = (m - 1.0) * img / ((2.0 * m - 1.0) * img - m)

    return (img * 255.0 + 0.5).astype(np.uint8)


def _decompress_payload(payload):
    """Locate the ZIP entry in *payload* and deflate-decompress it.

    The Seestar prepends a variable number of zero bytes before the
    ZIP local-file header.  This function scans for ``PK\\x03\\x04``,
    parses the local-file header to find the start of the compressed
    data stream, and decompresses it with raw deflate.

    Returns
    -------
    bytes
        Decompressed pixel data.
    """
    pk = payload.find(_ZIP_LOCAL_SIG)
    if pk == -1:
        raise ValueError("ZIP local-file header (PK\\x03\\x04) not found")

    # ZIP local file header: 30 fixed bytes + filename_len + extra_len
    fname_len = struct.unpack_from('<H', payload, pk + 26)[0]
    extra_len = struct.unpack_from('<H', payload, pk + 28)[0]
    data_start = pk + 30 + fname_len + extra_len

    return zlib.decompress(payload[data_start:], -15)


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

def parse_header(buf):
    """Parse a 34-byte Seestar image frame header.

    Parameters
    ----------
    buf : bytes
        Exactly 34 bytes read from the image socket.

    Returns
    -------
    dict
        Parsed header fields:

        - ``magic`` (int): Must equal :data:`MAGIC_NUMBER` (0x03C3).
        - ``version`` (int): Protocol version.
        - ``length`` (int): Payload size in bytes.
        - ``is_big_endian`` (int): Endianness flag.
        - ``img_type`` (int): 1 = preview, 5 = stacked.
        - ``data_type`` (int): Data format identifier.
        - ``frame_id`` (int): Frame ID.
        - ``width`` (int): Image width in pixels.
        - ``height`` (int): Image height in pixels.
        - ``hfd_x`` (int): Half-flux-diameter X (reserved).
        - ``hfd_y`` (int): Half-flux-diameter Y (reserved).
        - ``hfd`` (int): Half-flux-diameter value (reserved).
        - ``can_debayer`` (int): Bayer pattern flag (reserved).
        - ``image_id`` (int): Sequential frame counter.

    Raises
    ------
    ValueError
        If *buf* is not exactly 34 bytes.
    """
    if len(buf) != HEADER_SIZE:
        raise ValueError(
            f"Header must be {HEADER_SIZE} bytes, got {len(buf)}"
        )

    # Unpack all uint16 fields in one go, plus the uint32 length.
    magic = struct.unpack_from('>H', buf, 0)[0]
    version = struct.unpack_from('>H', buf, 2)[0]
    length = struct.unpack_from('>I', buf, 6)[0]
    width = struct.unpack_from('>H', buf, 16)[0]
    height = struct.unpack_from('>H', buf, 18)[0]
    hfd_x = struct.unpack_from('>H', buf, 20)[0]
    hfd_y = struct.unpack_from('>H', buf, 22)[0]
    hfd = struct.unpack_from('>H', buf, 24)[0]
    can_debayer = struct.unpack_from('>H', buf, 26)[0]
    image_id = struct.unpack_from('>H', buf, 28)[0]

    return {
        'magic': magic,
        'version': version,
        'length': length,
        'is_big_endian': buf[12],
        'img_type': buf[13],
        'data_type': buf[14],
        'frame_id': buf[15],
        'width': width,
        'height': height,
        'hfd_x': hfd_x,
        'hfd_y': hfd_y,
        'hfd': hfd,
        'can_debayer': can_debayer,
        'image_id': image_id,
    }


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _recv_exact(sock, n):
    """Read exactly *n* bytes from *sock*, raising on premature close."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), _RECV_BUF))
        if not chunk:
            raise ConnectionError(
                f"Connection closed after {len(buf)}/{n} bytes"
            )
        buf.extend(chunk)
    return bytes(buf)


def _send_json(sock, method):
    """Send a JSON-RPC message over the image socket."""
    msg = json.dumps({"id": 2, "method": method}) + "\r\n"
    sock.sendall(msg.encode())


def _make_socket(ip, port, timeout=10):
    """Create and connect a TCP socket with the same options as the app."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _RECV_BUF)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _RECV_BUF)
    sock.connect((ip, port))
    sock.settimeout(None)  # back to blocking for reads
    return sock


def _read_frame(sock):
    """Read one binary image frame (header + payload) from *sock*.

    The Seestar image socket carries both binary frames and JSON-RPC
    responses (e.g. heartbeat acks) on the same connection.  This
    function synchronises on the magic number ``0x03C3``, skipping
    any interleaved JSON text.

    Returns
    -------
    tuple[dict, bytes]
        ``(header_dict, image_payload)``

    Raises
    ------
    ConnectionError
        If the socket closes mid-read.
    """
    # Synchronise: find the 2-byte magic, skipping JSON responses
    while True:
        first = _recv_exact(sock, 1)

        if first[0] == 0x03:
            # Possible magic — check second byte
            second = _recv_exact(sock, 1)
            if second[0] == 0xC3:
                break
            # False alarm — keep scanning

        elif first[0] == ord('{'):
            # JSON response (heartbeat ack, etc.) — consume until \r\n
            _consume_json_line(sock, first)

        # Else: skip stray byte (zero padding, etc.)

    # Read remaining 32 bytes of header (we already consumed bytes 0-1)
    rest = _recv_exact(sock, HEADER_SIZE - 2)
    raw_header = b'\x03\xC3' + rest
    header = parse_header(raw_header)

    payload = _recv_exact(sock, header['length'])
    return header, payload


def _consume_json_line(sock, first_byte):
    """Read and discard a JSON-RPC line starting with *first_byte*."""
    buf = bytearray(first_byte)
    while not buf.endswith(b'\r\n'):
        buf.extend(_recv_exact(sock, 1))
        if len(buf) > 4096:
            break  # safety limit


# ---------------------------------------------------------------------------
# One-shot image grab
# ---------------------------------------------------------------------------

def get_live_image(ip=None, port=IMAGE_PORT, method="get_stacked_img",
                   filename=None):
    """Connect, grab a single image frame, and disconnect.

    This is the simplest way to get the current live-stacked image from
    the Seestar.  It opens a TCP connection, requests one frame, reads
    the binary response, and closes the socket.

    If *filename* is given the image is also saved to disk.  PNG and
    JPEG files get an automatic stretch to bring out faint nebulosity.
    Use a ``.fits`` extension to save the full 16-bit data losslessly
    (requires ``astropy``).

    Parameters
    ----------
    ip : str, optional
        Seestar IP address.  Defaults to
        :data:`connection.DEFAULT_IP <seestarpy.connection.DEFAULT_IP>`
        (auto-discovered via mDNS).
    port : int, optional
        Image stream port.  Default is :data:`IMAGE_PORT` (4800).
    method : str, optional
        JSON-RPC method to request a frame.  One of:

        - ``"get_stacked_img"`` (default) — latest stacked image.
        - ``"get_current_img"`` — current single frame / preview.

    filename : str, optional
        If provided, save the image to this path.  The extension
        determines the format (``.png``, ``.jpg``, ``.fits``, etc.).

    Returns
    -------
    tuple[dict, bytes]
        ``(header, payload)`` where *header* is the parsed 34-byte
        header dict and *payload* is the raw (compressed) image payload.
        Pass both to :func:`decode_payload` to get a NumPy array, or
        to :func:`save_image` to write a file.

    Examples
    --------
    ::

        >>> from seestarpy import stream
        >>> stream.get_live_image(filename="latest.png")   # auto-stretched
        >>> stream.get_live_image(filename="raw.fits")     # 16-bit FITS
        >>> header, payload = stream.get_live_image()
        >>> pixels = stream.decode_payload(payload, header)
    """
    if ip is None:
        ip = DEFAULT_IP
    sock = _make_socket(ip, port)
    try:
        _send_json(sock, method)
        header, payload = _read_frame(sock)
    finally:
        sock.close()

    if filename is not None:
        save_image(payload, header, filename)

    return header, payload


# ---------------------------------------------------------------------------
# Persistent streaming session
# ---------------------------------------------------------------------------

class StreamSession:
    """Manages a persistent image streaming connection.

    Created by :func:`start_stream`.  Call :meth:`stop` (or pass to
    :func:`stop_stream`) to cleanly shut down.

    Attributes
    ----------
    ip : str
        Seestar IP address.
    port : int
        TCP port in use.
    is_running : bool
        ``True`` while the stream is active.
    """

    def __init__(self, ip, port, sock, on_image):
        self.ip = ip
        self.port = port
        self.is_running = True
        self._sock = sock
        self._on_image = on_image
        self._stop_event = threading.Event()
        self._reader_thread = None
        self._heartbeat_thread = None
        self._latest_frame = None  # (header, stretched_uint8) for show()
        self._poll_stacked = False  # request stacked images in heartbeat

    # -- background threads ------------------------------------------------

    def _heartbeat_loop(self):
        """Send ``test_connection`` every :data:`HEARTBEAT_INTERVAL` seconds.

        When the live display is active, alternates with
        ``get_stacked_img`` requests to fetch the nice RGB image.
        """
        tick = 0
        while not self._stop_event.wait(HEARTBEAT_INTERVAL):
            try:
                if self._poll_stacked and tick % 2 == 0:
                    _send_json(self._sock, "get_stacked_img")
                else:
                    _send_json(self._sock, "test_connection")
            except OSError:
                break
            tick += 1

    def _reader_loop(self):
        """Continuously read frames and deliver them to the callback."""
        while not self._stop_event.is_set():
            try:
                header, payload = _read_frame(self._sock)
            except (ConnectionError, ValueError, OSError) as exc:
                if not self._stop_event.is_set():
                    print(f"Stream read error: {exc}")
                break
            if self._on_image is not None:
                try:
                    self._on_image(header, payload)
                except Exception as exc:
                    print(f"on_image callback error: {exc}")
        self.is_running = False

    # -- matplotlib live display -------------------------------------------

    def _display_callback(self, header, payload):
        """Internal callback that decodes and stretches each frame."""
        import numpy as np

        try:
            arr = decode_payload(payload, header)
        except ValueError:
            return  # skip ack/keepalive frames

        if arr.ndim == 2:
            # Single-channel Bayer → convert to pseudo-RGB for display
            arr = np.stack([arr, arr, arr], axis=2)

        self._latest_frame = (header, _auto_stretch(arr))

    def show(self):
        """Open a live matplotlib window showing streamed frames.

        This method **blocks** the main thread (runs the matplotlib
        event loop).  Closing the window stops the stream.

        The display auto-stretches each frame with :func:`_auto_stretch`
        so faint nebulosity is visible.  Frame metadata is shown in the
        window title.

        .. note::
            Requires ``matplotlib``.  Must be called from the main
            thread (which is normal for interactive / script usage).

        Examples
        --------
        ::

            >>> session = stream.start_stream()
            >>> session.show()          # blocks until window is closed

        Or as a one-liner via :func:`start_stream`::

            >>> stream.start_stream(with_matplotlib=True)
        """
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation

        # Request an initial stacked frame immediately and enable
        # periodic polling so the display gets the nice RGB image
        # rather than the raw Bayer preview.
        self._poll_stacked = True
        try:
            _send_json(self._sock, "get_stacked_img")
        except OSError:
            pass

        fig, ax = plt.subplots()
        ax.set_axis_off()
        fig.tight_layout(pad=0)
        im = [None]  # mutable ref for the closure

        def _update(_frame_number):
            frame = self._latest_frame
            if frame is None:
                return
            header, arr8 = frame
            if im[0] is None:
                im[0] = ax.imshow(arr8)
            else:
                im[0].set_data(arr8)
            fig.suptitle(
                f"Seestar {self.ip}  |  "
                f"{header['width']}x{header['height']}  |  "
                f"frame {header['image_id']}  |  "
                f"{'stacked' if header['img_type'] == IMG_TYPE_STACKED else 'preview'}"
            )

        anim = FuncAnimation(fig, _update, interval=500, cache_frame_data=False)  # noqa: F841
        try:
            plt.show()  # blocks until window closed
        finally:
            self._poll_stacked = False
            self.stop()

    # -- lifecycle ---------------------------------------------------------

    def _start_threads(self):
        """Spin up the heartbeat and reader daemon threads."""
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="seestar-heartbeat"
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="seestar-reader"
        )
        self._heartbeat_thread.start()
        self._reader_thread.start()

    def stop(self):
        """Stop streaming and close the connection.

        Safe to call multiple times.
        """
        if not self.is_running and self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            _send_json(self._sock, "stop_streaming")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=5)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)
        self.is_running = False


def start_stream(ip=None, port=IMAGE_PORT, on_image=None,
                 with_matplotlib=False):
    """Start a persistent image stream from the Seestar.

    Opens a TCP connection to the Seestar's image port and begins
    receiving frames continuously.  Each frame is delivered to the
    *on_image* callback on a background thread.

    A heartbeat (``test_connection``) is sent every
    :data:`HEARTBEAT_INTERVAL` seconds to keep the connection alive.

    Parameters
    ----------
    ip : str, optional
        Seestar IP address.  Defaults to
        :data:`connection.DEFAULT_IP <seestarpy.connection.DEFAULT_IP>`.
    port : int, optional
        Image stream port.  Default is :data:`IMAGE_PORT` (4800).
    on_image : callable, optional
        ``on_image(header: dict, data: bytes)`` called for each frame.
        *header* is the parsed 34-byte header dict; *data* is the raw
        image payload.
    with_matplotlib : bool, optional
        If ``True``, open a live matplotlib window that displays each
        frame as it arrives (auto-stretched).  The call **blocks** until
        the window is closed, then the stream is stopped automatically.
        Your *on_image* callback (if any) is still called for every
        frame alongside the display.

    Returns
    -------
    StreamSession
        Session handle — call ``session.stop()`` or pass to
        :func:`stop_stream` to shut down.

    Examples
    --------

    Live display (blocks until window closed)::

        >>> from seestarpy import stream
        >>> stream.start_stream(with_matplotlib=True)

    Custom callback::

        >>> frames = []
        >>> def collect(header, data):
        ...     frames.append((header, data))
        ...     if len(frames) >= 5:
        ...         session.stop()
        >>> session = stream.start_stream(on_image=collect)
    """
    if ip is None:
        ip = DEFAULT_IP
    sock = _make_socket(ip, port)

    session = StreamSession(ip, port, sock, on_image)

    if with_matplotlib:
        # Wrap the user's callback so each frame also feeds the display
        user_cb = on_image

        def _on_image_with_display(header, payload):
            session._display_callback(header, payload)
            if user_cb is not None:
                user_cb(header, payload)

        session._on_image = _on_image_with_display

    _send_json(sock, "begin_streaming")
    session._start_threads()

    if with_matplotlib:
        session.show()

    return session


def stop_stream(session):
    """Stop a streaming session started by :func:`start_stream`.

    Parameters
    ----------
    session : StreamSession
        The session to stop.
    """
    session.stop()


# ---------------------------------------------------------------------------
# RTSP helper
# ---------------------------------------------------------------------------

def build_rtsp_url(ip=None, port=RTSP_PORT):
    """Build an RTSP URL for the Seestar's live video feed.

    This returns the URL used by the official app to connect to the
    Seestar's RTSP server.  You can open it with ``ffplay``, VLC, or
    OpenCV's ``VideoCapture``.

    Parameters
    ----------
    ip : str, optional
        Seestar IP address.  Defaults to
        :data:`connection.DEFAULT_IP <seestarpy.connection.DEFAULT_IP>`.
    port : int, optional
        RTSP port.  Default is :data:`RTSP_PORT` (4554) for the
        telephoto camera.  Use :data:`RTSP_PORT_WIDE` (4555) for the
        wide-angle camera.

    Returns
    -------
    str
        RTSP URL, e.g. ``"rtsp://192.168.1.246:4554/stream"``.

    Examples
    --------
    ::

        >>> from seestarpy import stream
        >>> stream.build_rtsp_url()
        'rtsp://192.168.1.246:4554/stream'
        >>> stream.build_rtsp_url(port=stream.RTSP_PORT_WIDE)
        'rtsp://192.168.1.246:4555/stream'
    """
    if ip is None:
        ip = DEFAULT_IP
    return f"rtsp://{ip}:{port}/stream"
