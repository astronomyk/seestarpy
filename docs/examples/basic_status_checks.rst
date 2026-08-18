Checking the Seestar's Status
=============================

There are three levels at which you can ask a Seestar what it is doing,
and they suit different jobs:

#. the **ASCII dashboard** — one call, everything a human wants to see;
#. **named helpers** in :mod:`seestarpy.status` — small typed answers that
   are easy to put in an ``if``;
#. **raw queries** in :mod:`seestarpy.raw` — the firmware's own state
   dictionaries, when you need a field nobody wrapped yet.

Everything on this page accepts ``ips=`` for querying several scopes at
once (see :doc:`basic_connection`).

If you would rather watch a screen than poll in a loop, the web dashboard
does all of this for you and updates itself — see :doc:`live_dashboard`.


Status dashboard
----------------

The easiest way to see everything at a glance:

.. code-block:: python

   from seestarpy import status

   print(status.status_bar())

This prints a five-column ASCII table:

.. code-block:: text

   |================|================|================|================|==========|
   | View           | Coordinates    | Observation    | Initialisation | Seestar  |
   |================|================|================|================|==========|
   | MODE           | TARGET RA/DEC  | LP FILTER      | DARK FRAME     | BATTERY  |
   | STATE          | CURRENT RA/DEC | EXPOSURE TIME  | FOCUS POSITION | FREE MB  |
   | ERROR          | ALT  AZ  COMP  | STACK    DROP  | PLATE SOLVE    | EQ_MODE  |
   | TARGET NAME    | BALANCE ANGLE  | TRACKING       | SOLVE ERROR    | TIME     |
   | STAGE          | ARCSEC / PIX   | DITHER         | GAIN           | FIRMWARE |
   |================|================|================|================|==========|

Each cell is filled from a live query, so one ``status_bar()`` call is
several round-trips — fine every few seconds, not every 100 ms.

For programmatic use, ask for the same values as data instead of a table:

.. code-block:: python

   values = status.status_bar(return_type="dict")

That is the convenient way to log a whole night to CSV without parsing
your own output back out of a string.


Named helpers
-------------

:mod:`seestarpy.status` wraps the interesting fields as functions that
return a plain value rather than a nested reply dictionary:

.. code-block:: python

   from seestarpy import status

   status.get_firmware_version()   # '8.46'
   status.get_serial_number()      # 'a3497936'   (alias: status.get_sn)

   status.is_parked()              # False
   status.is_tracking()            # True
   status.is_eq_mode()             # True

   status.get_target_name()        # 'M 81'
   status.get_exposure()           # 20000   (milliseconds)

``get_filter`` is the one that hands back the whole reply rather than a
bare value — the position is under ``'result'``:

.. code-block:: python

   status.get_filter()["result"]   # 0 = dark, 1 = IR-cut, 2 = LP / narrow-band

The booleans are what you want in a script, because they answer the
question directly:

.. code-block:: python

   if status.is_parked():
       ssp.open()

Coordinates come back as one merged dictionary:

.. code-block:: python

   status.get_coords()
   # {'ra': 13.398, 'dec': 54.925, 'alt': 42.3, 'az': 312.7}

   status.azimuth_to_compass(312.7)    # 'NW'

RA is in decimal hours, everything else in degrees — the same convention
as the rest of seestarpy.  ``get_coords`` raises ``ValueError`` if the
mount has not been initialised yet (it cannot report a position before it
has been opened), which is a useful readiness check in itself.

The full mount state in one call:

.. code-block:: python

   status.get_mount_state()
   # {'move_type': 'none', 'close': False, 'tracking': True, 'equ_mode': True}

``close`` here means "arm parked", not "connection closed".


Plate scale
-----------

:func:`~seestarpy.status.pixel_scale` returns arcseconds per pixel, derived
from the focal length the device itself reports:

.. code-block:: python

   status.pixel_scale()        # 2.39 on an S50 telephoto (250 mm)
                               # 3.74 on the S30 Pro wide camera (160 mm)

Deriving it rather than hard-coding it means the number stays right across
models and cameras.  This is what converts a dither throw in pixels to
arcminutes, and it is what you need to turn a measured FWHM in pixels into
arcseconds of seeing.


Telescope state, raw
--------------------

When you need a field that has no helper, go to the firmware's own state
dictionaries:

.. code-block:: python

   from seestarpy import raw

   # Overall app state: what stage each subsystem is in
   raw.iscope_get_app_state()

   # Device state — big.  Ask for just the blocks you need:
   raw.get_device_state()                      # everything
   raw.get_device_state(keys=["mount"])        # one block
   raw.get_device_state(keys=["device", "pi_status", "storage"])

   # View and camera state
   raw.get_view_state()
   raw.get_camera_state()
   raw.get_camera_info()

   # The whole settings dictionary (exposure, dither, filters, …)
   raw.get_setting()

``get_device_state`` is the workhorse: the ``device`` block has the model,
serial and firmware version, ``station`` has the Wi-Fi address and signal,
``pi_status`` has battery, temperature and charge state, ``storage`` has
free space, and ``mount`` has the position and tracking flags.  Passing
``keys=`` keeps the reply small, which matters when you are polling.


Mount position
--------------

.. code-block:: python

   raw.scope_get_equ_coord()       # current RA/Dec  ← prefer this one
   raw.scope_get_horiz_coord()     # Alt/Az
   raw.scope_get_track_state()

.. note::
   There is also a ``scope_get_ra_dec``, and it is a trap worth knowing
   about.  That method belongs to the **image stream** (port 4800), where
   it doubles as the heartbeat; on the command socket firmware 8.x
   rejects it with ``code 103``.  seestarpy's wrapper detects that and
   falls back for you, but ``scope_get_equ_coord`` is the method the
   official app uses on every firmware, so reach for it directly.


Focus, filter and exposure
--------------------------

.. code-block:: python

   raw.get_focuser_position()
   raw.get_wheel_position()
   raw.get_wheel_setting()

   raw.get_last_solve_result()     # the most recent plate solve
   raw.get_solve_result()          # the solve in progress
   raw.get_stack_info()            # frames stacked / dropped so far
   raw.get_disk_volume()           # free space on the eMMC


Wi-Fi or wired?
---------------

A scope with the USB-C port in network mode is reachable on *two*
addresses — its Wi-Fi lease and its wired one — and the firmware has no
field saying which one your connection is using.
:func:`~seestarpy.raw.get_link_type` works it out by comparing the address
you connected to against the address the Wi-Fi interface claims:

.. code-block:: python

   raw.get_link_type(ips="all")
   # {'97783b61': {'link': 'wired', 'ip': '192.168.1.55',
   #               'station_ip': '192.168.1.83',
   #               'typec_mode': 'net', 'usb_en_eth': True},
   #  'ce545589': {'link': 'wifi',  'ip': '192.168.1.106',
   #               'station_ip': '192.168.1.106',
   #               'typec_mode': 'file', 'usb_en_eth': False}}

Results are keyed by serial number, so it is safe to run across a fleet.
See :doc:`changing_seestar_settings` for how to switch a port role.


Observation plan status
-----------------------

.. code-block:: python

   from seestarpy import plan

   vp = plan.get_running_plan()
   if vp and vp["state"] == "working":
       print(f"Running: {vp['plan']['plan_name']}")
       for t in vp["plan"]["list"]:
           print(f"  {t['target_name']}: {t.get('state', 'pending')}")

See :doc:`observation_plans` for full plan documentation.


Live events instead of polling
------------------------------

Everything above *asks*.  The Seestar also *tells*: it pushes unsolicited
event messages down the command connection whenever something happens — a
sub was stacked, a plate solve finished, the battery level changed.
Listening beats polling when you want to react promptly without hammering
the scope.

.. code-block:: python

   import seestarpy as ssp
   from seestarpy.events import event_stream

   ssp.start_listener()            # background thread, returns immediately

   # ... later, from anywhere in your program ...
   event_stream.LATEST_STATE["Stack"]
   # {'Event': 'Stack', 'stacked_frame': 204, 'dropped_frame': 6, ...}

   ssp.stop_listener()

:data:`~seestarpy.events.event_stream.LATEST_STATE` is a dictionary holding
the most recent message of each event type, keyed by event name
(``"Stack"``, ``"View"``, ``"PlateSolve"``, ``"PiStatus"``, …).  A rolling
buffer of the last 500 raw messages is kept in
:data:`~seestarpy.events.event_stream.LATEST_LOGS` if you want the history
rather than the latest value.

.. note::
   The listener follows :data:`~seestarpy.connection.DEFAULT_IP` and
   monitors **one** scope.  For several scopes at once, use
   :doc:`live_dashboard`, which runs an independent event connection and
   image stream per scope.

The event payloads are documented as dataclasses in
:mod:`seestarpy.events.event_definitions`, which is the quickest way to
find out what fields a given event carries.
