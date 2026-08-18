Live Image Streaming
====================

While a Seestar is observing it keeps a running stack going and makes the
progressively-improving image available over a binary socket on **port
4800** (telephoto) or **4804** (the S30 Pro's wide camera).  The ``stream``
module grabs single frames, streams them continuously, or just puts them
on screen.

This is a different channel from the JSON-RPC command socket, and a
different one again from the RTSP video feed described at the end of this
page.  The binary stream is where the *stacked* image lives.

.. note::
    Decoding needs NumPy, and JPEG frames additionally need Pillow.  Both
    come with ``pip install "seestarpy[dashboard]"``.  FITS output needs
    ``astropy``.


Peek at the current stack
-------------------------

The lowest-friction way to see what the Seestar is currently imaging —
one line, no file written, just a matplotlib window:

.. code-block:: python

    from seestarpy import stream

    stream.show_current_stack()

The frame is auto-stretched with a midtone transfer function so faint
nebulosity is visible.  The window title shows the Seestar IP,
resolution, frame number, and whether it's a stacked or preview image.

For multiple Seestars, pass ``ips="all"`` (or a list) and all frames are
fetched in parallel and tiled into a single subplot-grid figure:

.. code-block:: python

    from seestarpy import connection as conn

    conn.discover()
    stream.show_current_stack(ips="all")
    stream.show_current_stack(ips=[1, 2])         # specific scopes
    stream.show_current_stack(port=stream.IMAGE_PORT_WIDE)  # wide camera

Returns ``(header, arr8)`` for a single scope or
``{ip: (header, arr8)}`` for many — handy if you want to keep the
displayed pixels for further processing.  In the multi-scope form, a scope
that failed maps to the exception instance instead of a tuple, so check
before you index:

.. code-block:: python

    frames = stream.show_current_stack(ips="all", block=False)
    for ip, result in frames.items():
        if isinstance(result, Exception):
            print(f"{ip}: {result}")


Grabbing a single live image
----------------------------

The simplest use case — download the latest stacked image and save it as a
stretched PNG that reveals faint nebulosity:

.. code-block:: python

    from seestarpy import stream

    stream.get_live_image(filename="latest.png")

That's it.  The IP address defaults to the auto-discovered
``connection.DEFAULT_IP`` (see :doc:`basic_connection`), and the PNG is
auto-stretched with a midtone transfer function so faint structure is
visible.

If you want a lossless 16-bit FITS file instead (for further processing in
PixInsight, Siril, etc.), just change the extension:

.. code-block:: python

    stream.get_live_image(filename="latest.fits")

.. note::
    FITS output requires ``astropy``.  Install it with
    ``pip install astropy``.  A FITS file only makes sense for a **Raw**
    frame — see `Raw or JPEG?`_ below.

``get_live_image`` opens a socket, requests one frame, skips past any
zero-length keepalives, and closes.  If the scope is not stacking there is
no stacked image to send, and by default the call falls back to
``get_current_img`` so you get *something* renderable:

.. code-block:: python

    stream.get_live_image(fallback=False)     # insist on a real stack
    # RuntimeError if the scope isn't stacking

On a slow Wi-Fi link a 50 MB frame takes tens of seconds; ``read_timeout``
(default 30 s) bounds how long any single read may stall.


Working with the raw pixel data
-------------------------------

If you want to manipulate the image in Python directly, use
:func:`~seestarpy.stream.decode_payload`:

.. code-block:: python

    from seestarpy import stream

    header, payload = stream.get_live_image()
    pixels = stream.decode_payload(payload, header)

    print(pixels.shape)   # (1920, 1080, 3) on an S50 stacked frame
    print(pixels.dtype)   # uint16 — linear, unstretched

Stacked frames decode to ``(height, width, 3)``; preview frames are a
single-channel Bayer array, ``(height, width)``.  The header dict carries
the metadata:

.. code-block:: python

    print(header['width'], header['height'])
    print(header['img_type'])                 # 5 = stacked, 4 = JPEG stack,
                                              # 1 = preview, 0 = ack
    print(header['image_id'])                 # sequential frame counter
    print(header['hfd'])                      # half-flux diameter (focus quality)
    print(header['length'])                   # payload size in bytes

Two helpers save you from re-deriving the frame-type logic, which has more
edge cases than it looks:

.. code-block:: python

    stream.is_image_frame(header)     # False for acks/keepalives
    stream.is_stacked_frame(header)   # True for both raw and JPEG stacks

To get something displayable regardless of what the firmware sent, use
:func:`~seestarpy.stream.to_display8` rather than stretching by hand — it
makes the "stretch unless it is already 8-bit" decision for you:

.. code-block:: python

    arr8 = stream.to_display8(pixels)               # (H, W, 3) uint8
    arr8 = stream.to_display8(pixels, stretch=False)  # plain linear scale


Raw or JPEG?
------------

Firmware 8.46 added an ``image_transfer_mode`` setting that changes what
crosses the wire.  Measured on an 8 MP S30 Pro over Wi-Fi:

=========  ============  =========  ========  ===================================
mode       ``img_type``  size       time      ``decode_payload`` gives you
=========  ============  =========  ========  ===================================
``Raw``    5             ~49.8 MB   ~30 s     linear **uint16**, needs stretching
``Jpg``    4             ~2.5 MB    ~5 s      **uint8**, already stretched
=========  ============  =========  ========  ===================================

.. code-block:: python

    from seestarpy import raw

    raw.get_preview_setting()             # None on firmware older than 8.46
    raw.set_image_transfer_mode("Jpg")    # twentyfold faster refresh
    raw.set_image_transfer_mode("Raw")    # linear data for processing

**Always check the dtype** of what ``decode_payload`` hands back rather
than assuming uint16.  A JPEG frame has already been tone-mapped by the
firmware and that cannot be undone, so stay in ``Raw`` if the pixels are
destined for photometry or your own stretch.

.. warning::
    ``image_transfer_mode`` is a persistent device setting shared with the
    phone app, not a per-connection option.  See
    :doc:`changing_seestar_settings`.

Older firmware has no such setting and always sends ``Raw``.  On the raw
path the pixels arrive either ZIP-compressed (older firmware) or
uncompressed (S30 Pro, firmware 7.75+); ``decode_payload`` accepts both, so
you do not have to care which.


Preview vs stacked image
-------------------------

By default ``get_live_image`` requests the accumulated stacked image.  To
grab a single unstacked preview frame instead:

.. code-block:: python

    header, payload = stream.get_live_image(method="get_current_img")

A preview is the live-view frame — useful when the scope is slewing,
focusing or idle and has no stack to show.  It comes back as raw 16-bit
Bayer data (one channel, undebayered).


Live display with matplotlib
-----------------------------

The easiest way to watch the stacked image build up in real time — one line:

.. code-block:: python

    from seestarpy import stream

    stream.start_stream(with_matplotlib=True)

This opens a matplotlib window showing each new stacked frame as it arrives,
auto-stretched to reveal faint nebulosity.  The window title shows the Seestar
IP, resolution, frame number, and image type.  **Close the window to stop
streaming.**

.. note::
    The Seestar sends a new stacked frame every time it finishes
    integrating, so during active observation the display updates every
    few seconds.

You can combine the live display with your own callback — for example, to
save every frame to disk while also watching:

.. code-block:: python

    def save_each(header, payload):
        stream.save_image(payload, header, f"frame_{header['image_id']:04d}.png")

    stream.start_stream(on_image=save_each, with_matplotlib=True)

The callback runs on the stream's background thread and receives
``(header, payload)`` — the same pair ``get_live_image`` returns.  Keep it
quick: the socket is not being read while your callback runs.  A heartbeat
is sent every few seconds to keep the connection alive.

If you need full control over the display, call
:meth:`~seestarpy.stream.StreamSession.show` directly:

.. code-block:: python

    session = stream.start_stream()
    # ... do other setup ...
    session.show()   # blocks until window closed, then stops stream

    stream.stop_stream(session)   # or stop it yourself, without a window

.. note::
    A **parked or idle** Seestar has no image to send.  It answers with
    keepalive acks and then drops the idle connection, so a request made
    before you have opened the arm and started a view fails rather than
    returning a frame.  ``get_live_image`` reports this as such; open the
    scope first.

For several scopes on one screen, don't build it yourself — the web
dashboard already does it, with its own connection per scope and adaptive
request pacing.  See :doc:`live_dashboard`.


A note on the wire format
-------------------------

Each frame is a **80-byte header** followed by the payload.  Only the first
34 bytes carry named fields; the true size is announced at offset 4 and the
rest is padding, so always trust ``header['header_size']`` instead of
assuming.  The reader syncs on the magic number ``0x03C3``, and the same
socket carries JSON-RPC heartbeat replies alongside the binary frames.

The full specification — field offsets, payload formats, the ZIP framing —
is in :doc:`../info/image_stream_protocol`.  You only need it if you are
writing your own reader; :func:`~seestarpy.stream.parse_header` and
:func:`~seestarpy.stream.decode_payload` handle it otherwise.


RTSP video stream
-----------------

The Seestar also has an RTSP video feed (live viewfinder, not the stacked
image).  This is useful for aiming, focusing, and monitoring in real time:

.. code-block:: python

    url = stream.build_rtsp_url()        # telephoto camera, port 4554
    # 'rtsp://192.168.1.246:4554/stream'

    stream.build_rtsp_url(port=stream.RTSP_PORT_WIDE)   # wide camera, 4555

You can open this with ``ffplay``, VLC, or OpenCV:

.. code-block:: bash

    ffplay rtsp://192.168.1.246:4554/stream

Or in Python with OpenCV:

.. code-block:: python

    import cv2
    cap = cv2.VideoCapture(stream.build_rtsp_url())
    while cap.isOpened():
        ret, frame = cap.read()
        if ret:
            cv2.imshow("Seestar Live", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    cap.release()

The RTSP resolution and quality are firmware settings (``rtsp_quality``,
``rtsp_width``, ``rtsp_height`` in the ``preview`` block) — see
:doc:`changing_seestar_settings`.
