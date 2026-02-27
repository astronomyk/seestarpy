Live Image Streaming
====================

The Seestar continuously stacks frames during observation and makes the
progressively-improving image available over a binary socket on port 4800.
The ``stream`` module lets you grab single frames or stream them in real time.


Grabbing a single live image
----------------------------

The simplest use case — download the latest stacked image and save it as a
stretched PNG that reveals faint nebulosity:

.. code-block:: python

    from seestarpy import stream

    stream.get_live_image(filename="latest.png")

That's it.  The IP address is auto-discovered via mDNS, and the PNG is
auto-stretched with a midtone transfer function so faint structure is visible.

If you want a lossless 16-bit FITS file instead (for further processing in
PixInsight, Siril, etc.), just change the extension:

.. code-block:: python

    stream.get_live_image(filename="latest.fits")

.. note::
    FITS output requires ``astropy``.  Install it with
    ``pip install astropy``.


Working with the raw pixel data
-------------------------------

If you want to manipulate the image in Python directly, use
:func:`~seestarpy.stream.decode_payload`:

.. code-block:: python

    from seestarpy import stream

    header, payload = stream.get_live_image()
    pixels = stream.decode_payload(payload, header)

    print(pixels.shape)   # (3840, 2160, 3) on S50 in 4K mode
    print(pixels.dtype)   # uint16

The array is ``(height, width, 3)`` with 16-bit RGB values.  The header dict
contains useful metadata:

.. code-block:: python

    print(header['width'], header['height'])  # 2160 3840
    print(header['img_type'])                 # 5 = stacked, 1 = preview
    print(header['image_id'])                 # sequential frame counter
    print(header['hfd'])                      # half-flux diameter (focus quality)


Multi-Seestar usage
-------------------

For multiple Seestars, pass the IP explicitly:

.. code-block:: python

    from seestarpy import connection as conn

    conn.find_available_ips(3)

    for name, ip in conn.AVAILABLE_IPS.items():
        stream.get_live_image(ip=ip, filename=f"{name}.png")


Preview vs stacked image
-------------------------

By default ``get_live_image`` requests the accumulated stacked image.  To grab
a single unstacked preview frame instead:

.. code-block:: python

    header, payload = stream.get_live_image(method="get_current_img")


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

If you need full control over the display, call
:meth:`~seestarpy.stream.StreamSession.show` directly:

.. code-block:: python

    session = stream.start_stream()
    # ... do other setup ...
    session.show()   # blocks until window closed, then stops stream


RTSP video stream
-----------------

The Seestar also has an RTSP video feed (live viewfinder, not the stacked
image).  This is useful for aiming, focusing, and monitoring in real time:

.. code-block:: python

    url = stream.build_rtsp_url()        # telephoto camera
    # 'rtsp://192.168.1.246:4554/stream'

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
