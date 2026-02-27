Image Stream Protocol — Reverse Engineering Notes
==================================================

.. note::
    This page documents the reverse engineering of the Seestar's live image
    streaming protocol, carried out in February 2026.  It is written to serve
    both as a human reference and as context for future AI-assisted development.


Background
----------

The Seestar Android app displays a progressively-improving stacked image
during observation.  This is *not* the RTSP video feed (which is the raw
camera viewfinder) — it is a separate binary socket that delivers the actual
stacked deep-sky image.

Understanding this protocol was needed to build the ``stream`` module in
seestarpy, which lets users grab live stacked images in Python.


Discovery: dual streaming architecture
---------------------------------------

The Seestar exposes **five** TCP ports, each serving a different purpose:

====  ========  ========================================================
Port  Protocol  Purpose
====  ========  ========================================================
4700  JSON-RPC  Command and control (already implemented in seestarpy)
4554  RTSP      Live H.264 video — telephoto camera (viewfinder)
4555  RTSP      Live H.264 video — wide-angle camera
4800  Binary    Live stacked images — telephoto camera
4804  Binary    Live stacked images — wide-angle camera
====  ========  ========================================================

The RTSP streams are standard H.264 video (``rtsp://<ip>:<port>/stream``)
decoded via FFmpeg in the app.  They show the raw camera feed and are useful
for aiming and focusing but do **not** show the stacked image.

Ports 4800 and 4804 are the interesting ones — they use a custom binary
framing protocol to deliver the progressively stacked image.


Methodology
-----------

The protocol was reverse-engineered in two phases:

1. **Static analysis** — The Seestar Android APK (v3.0.2) was decompiled with
   JADX.  The relevant Java classes were found under
   ``com.wss.rxscoketclient`` (socket I/O) and ``com.zwo.seestar.socket``
   (connection management).

2. **Live capture** — The protocol was confirmed by connecting to three live
   Seestar S50 telescopes and exchanging real data on port 4800.


Binary frame protocol
---------------------

Each frame on port 4800/4804 consists of a **34-byte header** followed by an
**image payload**.

Header format (34 bytes, big-endian)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

======  ======  =============  ==============================================
Offset  Size    Field          Notes
======  ======  =============  ==============================================
0-1     uint16  magic          Must be ``0x03C3`` (963 decimal)
2-3     uint16  version        Protocol version (observed: 2)
4-5     uint16  (gap)          Unused by the app's header parser
6-9     uint32  length         Image payload size in bytes (big-endian)
10-11   uint16  (gap)          Unused
12      byte    is_big_endian  Endianness flag
13      byte    img_type       1 = preview, 5 = stacked
14      byte    data_type      Data format identifier (observed: 3)
15      byte    frame_id       Frame identifier
16-17   uint16  width          Image width in pixels
18-19   uint16  height         Image height in pixels
20-21   uint16  hfd_x          Half-flux-diameter X
22-23   uint16  hfd_y          Half-flux-diameter Y
24-25   uint16  hfd            Half-flux-diameter value (focus quality)
26-27   uint16  can_debayer    Bayer pattern flag (1 = raw Bayer input)
28-29   uint16  image_id       Sequential frame counter
30-31   uint16  reserved5      Unused
32-33   uint16  reserved6      Unused
======  ======  =============  ==============================================

The magic number constant is defined as ``FileDealUtil.MAGIC_NUMBER = 963``
in the APK source (``com.wss.rxscoketclient.deal.FileDealUtil``).


Image payload formats
~~~~~~~~~~~~~~~~~~~~~

The payload format depends on the frame type.  There are **three** kinds of
frame, distinguished by ``img_type`` and ``data_type`` in the header:

Stacked frames (img_type=5, data_type=3)
"""""""""""""""""""""""""""""""""""""""""

Returned by ``get_stacked_img`` and during active observation.  The payload
is a **streaming ZIP archive** containing deflate-compressed raw pixel data.

Structure::

    [zero padding]  [ZIP local file header]  [deflate stream]

Specifically:

1. A variable number of zero bytes (observed: 46 bytes)
2. A ZIP local-file header (``PK\x03\x04``) with:

   - Version 4.5 (ZIP64)
   - Compression method: deflate (8)
   - Bit flag 0x0008 (data descriptor, streaming — sizes not in header)
   - Filename: ``raw_data``

3. The deflate-compressed pixel data

The decompressed data is **16-bit RGB** (48 bits per pixel)::

    height × width × 3 × sizeof(uint16) bytes

For a 4K S50: 3840 × 2160 × 3 × 2 = 49,766,400 bytes (decompressed from
~24 MB compressed).

This can be loaded directly into a NumPy array::

    np.frombuffer(raw, dtype=np.uint16).reshape((height, width, 3))

Preview frames (img_type=1, data_type=2)
""""""""""""""""""""""""""""""""""""""""

Pushed by ``begin_streaming`` (the live camera feed).  The payload is **raw
uncompressed 16-bit Bayer** data — a single channel before demosaicing::

    height × width × sizeof(uint16) bytes

For a standard S50: 1920 × 1080 × 2 = 4,147,200 bytes.  The
``can_debayer`` header field is set to 1.  Load as::

    np.frombuffer(payload, dtype=np.uint16).reshape((height, width))

Ack / keepalive frames (img_type=0)
""""""""""""""""""""""""""""""""""""

Sent periodically with ``width=0``, ``height=0``, and a tiny payload (4--17
bytes).  These should be silently skipped.

Socket multiplexing
~~~~~~~~~~~~~~~~~~~

A critical implementation detail: the image socket carries **both** binary
frames and JSON-RPC text responses on the same TCP connection.  Heartbeat
responses (``test_connection`` acks) arrive as ``\r\n``-terminated JSON
between binary frames.

The reader must synchronise on the magic number ``0x03C3`` and skip any
interleaved JSON lines (which start with ``{``).  See
``stream._read_frame()`` for the implementation.


JSON-RPC commands (same socket)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The image socket also accepts JSON-RPC commands, sent as
``\\r\\n``-terminated JSON strings:

.. code-block:: json

    {"method": "test_connection", "id": 1}
    {"method": "begin_streaming", "id": 2}
    {"method": "stop_streaming", "id": 2}
    {"method": "get_current_img", "id": 2}
    {"method": "get_stacked_img", "id": 2}

- ``test_connection`` — Heartbeat, must be sent every ~4 seconds to keep the
  connection alive.
- ``begin_streaming`` — Start continuous frame delivery.
- ``stop_streaming`` — Stop continuous frame delivery.
- ``get_stacked_img`` — Request a single stacked image frame.
- ``get_current_img`` — Request a single preview frame.


Connection lifecycle
~~~~~~~~~~~~~~~~~~~~

The official app follows this pattern:

1. Open TCP socket to port 4800 with ``TCP_NODELAY``, 64 KB buffers, keepalive
2. Start a heartbeat thread sending ``test_connection`` every 4000 ms
3. Send ``begin_streaming`` (or ``get_stacked_img`` for one-shot)
4. Read loop: 34-byte header → validate magic → read ``length`` bytes → process
5. Send ``stop_streaming`` → close socket


Observed resolutions
--------------------

Tested against three Seestar S50 units on the same network:

================  ===========  ===========
Seestar           Resolution   image_id
================  ===========  ===========
seestar.local     2160 × 3840  98
seestar-2.local   1080 × 1920  30
seestar-3.local   2160 × 3840  237
================  ===========  ===========

The 2160 × 3840 resolution comes from the S50's "enhanced" mode, which uses
sub-pixel dithering to populate a 4K grid from the native 1080p sensor.
seestar-2 was not in enhanced mode at the time of capture.


Key APK source files
--------------------

All paths relative to the decompiled APK (``sources/``):

- ``com/wss/rxscoketclient/SocketObservable.java`` — TCP socket + ReadThread
  (binary frame reader; the ``run()`` method was too complex for JADX to
  decompile — 1285 bytecode instructions)
- ``com/wss/rxscoketclient/deal/HeaderData.java`` — 34-byte header parser
- ``com/wss/rxscoketclient/deal/FileDealUtil.java`` — ``MAGIC_NUMBER = 963``,
  ``bytes2int()`` helper
- ``com/wss/rxscoketclient/deal/ImageEvent.java`` — Image metadata DTO
- ``com/zwo/seestar/socket/MainFileManager.java`` — JSON-RPC command senders
- ``com/zwo/seestar/socket/SocketManager.java`` — Connection lifecycle,
  heartbeat, retry logic
- ``com/zwo/kit/utils/RtspUtilsKt.java`` — RTSP URL builder


Data flow in the app
--------------------

::

    Telescope (port 4800)
        │
        ▼
    SocketObservable.ReadThread.run()
        │  1. Read 34-byte header
        │  2. Validate magic == 0x03C3
        │  3. Read `length` bytes of image payload
        │  4. Write payload to temp file on disk
        │  5. Create ImageEvent(header, filePath, fileSize)
        │
        ▼
    SocketObservable.SocketObserver.onNext(ImageEvent)
        │  Wrap in DataWrapper(state=1, data=imageEvent)
        │
        ▼
    SocketManager.onResponse(ImageEvent)
        │  Post to EventBus for UI subscribers
        │
        ▼
    UI fragments load image from imageEvent.getPath()


What's left to explore
----------------------

- **Wide camera stream (port 4804)** — Confirmed to accept the same protocol
  but not yet tested with live data.
- **Dual-pane live display** — During ``begin_streaming``, the telescope
  pushes preview frames (single subs) *and* the heartbeat can poll stacked
  frames.  A side-by-side matplotlib display (preview | stack) would let
  the user spot clouds in new subs while watching the stack improve.
- **Continuous streaming during active observation** — Does the telescope
  push stacked frames (img_type=5) automatically via ``begin_streaming``
  during observation, or only preview frames?  The exact cadence and frame
  types during active stacking need measurement.
- **RTSP integration** — The RTSP ports (4554/4555) use standard H.264.
  An OpenCV or ffmpeg-based live preview could complement the stacked-image
  stream.
