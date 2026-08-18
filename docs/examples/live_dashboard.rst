Live Dashboard
==============

When you are running more than one Seestar, the thing you actually want
is a single screen answering "are they all still doing what I asked?".
:mod:`seestarpy.dashboard` serves exactly that: it finds every Seestar on
the network by itself and gives each one a card showing what it is
imaging right now next to the numbers that tell you whether the run is
going well.

.. code-block:: bash

   pip install "seestarpy[dashboard]"
   python -m seestarpy.dashboard

A browser opens on the dashboard.  There is nothing to configure — no IP
addresses, no list of scopes, no restart when a scope joins later.

What a card shows
-----------------

Each card is one Seestar::

    ┌──────────────────────────────────────────────────┐
    │ a3497936 — 192.168.1.55  [WIFI]       ● stacking │
    ├─────────────────────────────┬────────────────────┤
    │                             │ RAW EXPOSURE       │
    │                             │ 10 s  gain 80      │
    │                             │ STACK TIME         │
    │                             │ 34.0 min  204 subs │
    │      the current stack      │ DROPPED            │
    │      (or the live view,     │ 2.9 %  6 frames    │
    │       if not stacking)      │ FILTER             │
    │                             │ IRCUT  dither 2.0' │
    │                             ├────────────────────┤
    │                             │ TARGET             │
    │                             │ NGC 869            │
    │                             │ RA / DEC           │
    │                             │ 2.320 h  +57.13°   │
    │                             │ ALT / AZ           │
    │                             │ 42.3°  312.7°  NW  │
    │                             │ VIEW STATUS        │
    │                             │ working  Stack     │
    │                             ├────────────────────┤
    │                             │ MOUNT              │
    │                             │ Equatorial tracking│
    │ STACKED             12 s ago│ BATTERY  62 %      │
    └─────────────────────────────┴────────────────────┘

The header gives the serial number, the address it is reachable on, and
whether that address is the Wi-Fi radio (``WIFI``) or the USB-C Ethernet
gadget (``LAN``).  The pill on the right is what the scope is doing:
``stacking``, ``autofocus``, ``idle``, ``parked``, or ``offline``.

The status column is grouped the way you read it — how the exposure is
going, where the scope is pointing, and how the hardware is holding up.
Values that matter turn colour with a label beside them: a dropped-frame
rate over 10 %, a battery under 30 %, a disk under 5 GB.

Stacked images are preferred over the live view.  When a scope is
stacking you see the accumulating stack; when it is slewing, focusing or
idle you get the live preview instead, and the tag in the corner of the
image says which one you are looking at.

Running it
----------

.. code-block:: python

   from seestarpy import dashboard

   dashboard.serve()                     # blocks until Ctrl-C

Keep control of the interpreter (useful in a notebook):

.. code-block:: python

   server = dashboard.serve(block=False, open_browser=False)
   print(server.url)                     # http://192.168.1.20:8080/
   ...
   server.stop()

By default the dashboard binds loopback only, because it has **no
authentication**.  Pass ``lan=True`` (or ``--lan``) to bind ``0.0.0.0``
and reach it from a phone or tablet elsewhere on the network::

   dashboard.serve(lan=True)

Command-line options
--------------------

.. code-block:: bash

   python -m seestarpy.dashboard --help

====================  ======================================================
``--host``            interface to bind (default ``127.0.0.1``)
``--lan``             bind ``0.0.0.0`` - reachable from the network
``--port``            port to serve on (default 8080)
``--no-browser``      don't open a browser window
``--rescan SECONDS``  gap between network discovery sweeps (default 60)
``--wide``            show the wide-angle camera (port 4804) instead of the
                      telephoto stream
``--verbose``         log every HTTP request
====================  ======================================================

Running it on a Raspberry Pi
----------------------------

The dashboard is a good fit for a Pi left on the network: the Pi does the
discovering, the event connections and the image fetching, and your laptop
or phone only ever speaks HTTP to it.

Discovery is a **UDP broadcast** (port 4720), so the Pi has to be on the
same LAN segment as the Seestars.  That is the one hard requirement — the
browser can be anywhere.

.. code-block:: bash

   pip install "seestarpy[dashboard]"
   python -m seestarpy.dashboard --lan --no-browser

On an ARMv6 Pi (Zero W), install NumPy and Pillow from piwheels first —
see :doc:`install_on_raspberry_pi`.  Note that in ``Raw`` mode the Pi has
to hold and stretch a 50 MB frame per scope; a Pi 4 or 5 handles that
comfortably, a Pi Zero will struggle with several scopes at once.  In
``Jpg`` mode there is nothing to stretch and it is cheap on any model.

As a service
^^^^^^^^^^^^

.. code-block:: ini

   # /etc/systemd/system/seestar-dashboard.service
   [Unit]
   Description=Seestar dashboard
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=pi
   ExecStart=/usr/bin/python3 -m seestarpy.dashboard --lan --no-browser
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target

.. code-block:: bash

   sudo systemctl enable --now seestar-dashboard

Reaching it over Tailscale
^^^^^^^^^^^^^^^^^^^^^^^^^^

Because the server binds every interface with ``--lan``, it is already
listening on the Tailscale interface — browse to the Pi's MagicDNS name,
e.g. ``http://raspberrypi:8080/``.  Nicer still, let Tailscale terminate
it:

.. code-block:: bash

   tailscale serve --bg 8080

That gives you HTTPS on the tailnet with no LAN exposure at all, in which
case you can drop ``--lan`` and bind loopback only.

.. warning::

   The dashboard has **no authentication**.  A tailnet is private, so
   this is fine there — but never put it behind ``tailscale funnel``,
   which publishes to the open internet.  The cards carry your serial
   numbers, targets and pointing.

The startup banner prints the Pi's LAN address, not its tailnet one: it
picks the interface of the default route.  Ignore it and use the MagicDNS
name.

How it works
------------

For each Seestar the dashboard holds two connections open:

- **Port 4700** — a persistent JSON-RPC connection.  Unsolicited events
  (``Stack``, ``View``, ``PiStatus``) arrive as the scope emits them, and
  a slow heartbeat polls ``get_device_state`` and friends so the card is
  still populated when the scope is idle and saying nothing.
- **Port 4800** — the binary image stream.  One frame is requested at a
  time rather than opening the continuous stream, because a preview frame
  is 16 MB and a raw stacked one 50 MB on an S30 Pro; the request pacing
  adapts to how long the last transfer actually took, so a slow Wi-Fi
  link throttles itself instead of saturating.

Making it much faster (firmware 8.46+)
--------------------------------------

The tag in the corner of each image reads ``STACKED · RAW`` or
``STACKED · JPG``.  That is the scope's ``image_transfer_mode`` setting,
and it is worth knowing about, because on an 8 MP S30 Pro over Wi-Fi the
difference is twentyfold:

=========  ===========  ========  =========================================
mode       frame size   time      what you get
=========  ===========  ========  =========================================
``Jpg``    ~2.5 MB      ~5 s      a finished, firmware-stretched JPEG
``Raw``    ~49.8 MB     ~30 s     linear 16-bit data, stretched by seestarpy
=========  ===========  ========  =========================================

In ``Jpg`` mode a card refreshes every few seconds and barely touches the
network.  To switch a scope over:

.. code-block:: python

   from seestarpy import raw

   raw.get_preview_setting()          # None on firmware older than 8.46
   raw.set_image_transfer_mode("Jpg")
   raw.set_image_transfer_mode("Jpg", ips="all")

.. warning::

   This is a **persistent device setting**, shared with the phone app —
   it is not scoped to the dashboard's connection, and it stays put until
   you change it back.  The dashboard therefore only *reports* the mode
   and never changes it for you.  Keep ``Raw`` if you want the linear
   data for your own processing: the JPEG has already been tone-mapped
   and that cannot be undone.

Firmware earlier than 8.46 has no such setting and always sends ``Raw``.

Frames are stretched with a screen-transfer function that solves for the
midtone rather than using a fixed curve, so the sky lands at a known
brightness whatever the exposure, gain or light pollution — a live
Seestar frame is faint enough that a fixed curve renders it nearly black.

Both connections reconnect on their own, and a scope that cannot be
reached is greyed out with the reason on its card rather than
disappearing.

.. note::

   Decoding the image stream needs NumPy and Pillow, which is what
   ``pip install "seestarpy[dashboard]"`` adds.  Without them the status
   half of every card still works and the image panel reports the missing
   dependency.

.. note::

   A card shows ``no image stream`` when the scope has no image to give —
   most often because it is parked or idle rather than observing.  The
   rest of its status keeps updating regardless.
