Observing with seestarpy
========================

This page walks through the essentials: slewing to a target, stacking
exposures, and shutting down cleanly.


Quickstart — three commands
---------------------------

Assuming you have already connected (see :doc:`basic_connection`):

.. code-block:: python

   import seestarpy as ssp

   ssp.open()
   ssp.goto_target("M42")
   ssp.start_stack()

``goto_target`` resolves the coordinates automatically via the
`CDS Sesame <https://cds.u-strasbg.fr/cgi-bin/Sesame>`_ name resolver
(SIMBAD/NED/VizieR), slews to the target, and runs a plate-solve loop.
``start_stack`` then begins stacking sub-exposures.

Each of these returns the firmware's JSON reply, and each accepts
``ips=`` to drive several Seestars at once.

.. note::
   The commands are **asynchronous**: ``goto_target`` returns as soon as
   the firmware accepts the slew, not when the scope has arrived.  A
   goto-plus-plate-solve typically takes 30–60 s.  Poll
   :func:`~seestarpy.status.get_mount_state` or
   :func:`~seestarpy.raw.get_view_state` if your script needs to wait —
   see :doc:`basic_status_checks`.


Using explicit coordinates
--------------------------

If you prefer to specify coordinates yourself, or are working offline:

.. code-block:: python

   ssp.goto_target("Mizar", ra=13.4, dec=54.9)

RA is in decimal hours [0, 24) and Dec is in decimal degrees [-90, 90].
This convention holds everywhere in seestarpy — hours for RA, degrees for
Dec.  Pass both or neither; one without the other raises ``ValueError``.

The ``target_name`` is not just a label: it is also the folder name the
Seestar files the resulting FITS frames under, so keep it filesystem-safe
and consistent between sessions if you plan to stack across nights.

To resolve a name without slewing anywhere:

.. code-block:: python

   from seestarpy.plan import resolve_name

   resolve_name("NGC 7000")      # (20.9917, 44.53)


Light-pollution filter
----------------------

Enable the LP filter for a target:

.. code-block:: python

   ssp.goto_target("M42", lp_filter=True)

Or toggle the filter wheel directly:

.. code-block:: python

   ssp.filter_wheel("lp")       # LP / narrow-band filter
   ssp.filter_wheel("ircut")    # open / IR-cut filter
   ssp.filter_wheel()           # read current position


Exposure time
-------------

.. code-block:: python

   ssp.exposure()                   # {'stack_l': 10000, 'continuous': 500}
   ssp.exposure(10)                 # 10 s subs for stacking
   ssp.exposure(30, which="stack_l")

Accepted sub lengths are **2, 5, 10, 20, 30 and 60 seconds**.  The 2 s and
5 s options are normally hidden behind the firmware's "expert mode";
seestarpy sets that flag for you.  Values above 100 are read as
milliseconds, so ``ssp.exposure(20000)`` and ``ssp.exposure(20)`` mean the
same thing.

``which="continuous"`` sets the live-view exposure instead — the frames you
see while aiming, not the ones that go into the stack.

Longer subs are not automatically better: they collect more signal per
frame but give the mount more time to smear, and a satellite or gust ruins
a bigger slice of the night.  10–30 s is the usual working range.


Focus
-----

.. code-block:: python

   ssp.focuser()                    # read current position, e.g. 1580
   ssp.focuser("auto")              # run the firmware auto-focus routine
   ssp.focuser(pos=1605)            # move to an explicit position

The travel range is roughly [1200, 2600] with the factory default near
1580.  Auto-focus needs stars in the field, so run it after the goto has
finished, not before.

.. warning::
   Auto-focus **aborts a running observation plan**, and the firmware will
   not restart the plan on its own.  If you are running a plan (see
   :doc:`observation_plans`), focus before you submit it.


Dithering
---------

Dithering nudges the mount by a small random offset every few subs.  It
matters for deep stacks: on an equatorially tracked field every sub lands
on the *same* pixels, so flat-field and dark residuals add up coherently
instead of averaging away.  Moving the field around the detector breaks
that correlation.

.. code-block:: python

   ssp.dither()
   # {'enabled': True, 'radius_arcmin': 2.39, 'radius_px': 60, 'every_n_subs': 5}

   ssp.dither(radius_arcmin=2.5, every_n_subs=5)   # configure (and enable)
   ssp.dither(radius_arcmin=3, interval_s=120)     # cadence in seconds instead
   ssp.dither(False)                               # undithered control run

The firmware stores the throw in *pixels*; ``dither()`` takes and reports
it in *arcminutes*, converting with the plate scale of the camera actually
attached (see :func:`~seestarpy.status.pixel_scale`), so the same number
means the same angle on an S50 telephoto and an S30 Pro wide camera.

A few rules of thumb:

- **2–3′** is a good radius.  A few tens of pixels already averages over
  pixel-scale flat error, while a large radius shrinks the sky area common
  to every sub.  Large-scale vignetting cannot be dithered away at any
  amplitude.
- **Every 5–6 subs** (~2 min at 20 s) is a good cadence.  Dither less
  often than that and a short stack only ever sees one position.
- Setting a radius or cadence without passing ``enabled`` turns dithering
  **on**, on the assumption that you are configuring it because you want
  it.  Pass ``enabled=False`` to configure it but leave it off.

.. note::
   Firmware ships with dithering **enabled**, so a run that is meant to be
   undithered has to say so explicitly.  Alt-azimuth mounts get a similar
   decorrelation for free from field rotation.


Stopping and parking
--------------------

.. code-block:: python

   # Stop stacking, but leave the camera running (saves the stack so far)
   ssp.raw.iscope_stop_view("Stack")

   # Stop imaging entirely
   ssp.stop_view()

   # Park the arm
   ssp.close()

   # Or shut the Seestar down completely
   ssp.raw.pi_shutdown(True)       # force=True to confirm

``close()`` parks in whichever mount mode the scope is currently in.  Pass
``eq_mode`` explicitly to change it while parking:

.. code-block:: python

   ssp.close(eq_mode=False)        # park into Alt-Az mode


Initial setup commands
----------------------

The first time you use seestarpy (or after a firmware update, or if the
scope has been off long enough to lose its clock), sync the time and
location.  Plate-solving and Alt-Az conversion both depend on them, and
``start_min`` in observation plans is interpreted against the scope's own
clock:

.. code-block:: python

   ssp.raw.pi_set_time()                          # sync to this machine's clock
   ssp.raw.set_user_location(lat=48.2, lon=16.4)  # Vienna, Austria

Check what the scope currently believes:

.. code-block:: python

   ssp.raw.pi_get_time()
   ssp.raw.get_user_location()

If you use an equatorial wedge:

.. code-block:: python

   ssp.set_eq_mode(True)      # park into EQ mode
   ssp.open()                 # raise the arm again

EQ mode requires the scope to be parked, which is why ``set_eq_mode``
parks it — you have to ``open()`` again afterwards.  For polar alignment
on a wedge:

.. code-block:: python

   ssp.raw.start_polar_align()
   ssp.raw.stop_polar_align()

See :doc:`changing_seestar_settings` for the rest of the device settings.


A complete session
------------------

Putting it together — a script that images one target for an hour and
parks itself:

.. code-block:: python

   import time
   import seestarpy as ssp
   from seestarpy import status

   # 1. House-keeping
   ssp.raw.pi_set_time()
   ssp.raw.set_user_location(lat=48.2, lon=16.4)

   # 2. Configure before slewing
   ssp.exposure(20)                              # 20 s subs
   ssp.dither(radius_arcmin=2.5, every_n_subs=5)

   # 3. Open, slew, focus, stack
   ssp.open()
   ssp.goto_target("M 81")
   time.sleep(60)                                # let the goto + solve finish
   ssp.focuser("auto")
   ssp.start_stack()

   # 4. Watch it work
   for _ in range(60):
       print(status.status_bar())
       time.sleep(60)

   # 5. Shut down
   ssp.stop_view()
   ssp.close()

Replace the ``sleep`` calls with real state polling (see
:doc:`basic_status_checks`) once you trust the sequence, and consider
handing the whole night to the scope with an observation plan
(:doc:`observation_plans`) so it keeps going if your laptop sleeps.


Low-level commands
------------------

The ``raw`` module gives direct access to every JSON-RPC command the
Seestar supports.  The high-level functions above are wrappers around
these, so when you need an option a wrapper does not expose, drop down a
level:

.. code-block:: python

   from seestarpy import raw

   raw.scope_move_to_horizon()
   raw.iscope_start_view(ra=13.4, dec=54.9, target_name="Mizar")
   raw.iscope_start_stack()
   raw.scope_goto(12, 88)              # slew without starting a view
   raw.scope_get_equ_coord()           # where is it actually pointing?
   raw.scope_speed_move(90, 3, 2)      # nudge: angle, speed, duration
   raw.play_sound(13)                  # make it beep, to find it in the dark

And if a method exists in the firmware that seestarpy has no wrapper for
yet, send it yourself:

.. code-block:: python

   raw.random_command("get_camera_info")
   raw.random_command("set_setting", {"heater_enable": True})

See the :doc:`../api/raw` API reference for the full list.
