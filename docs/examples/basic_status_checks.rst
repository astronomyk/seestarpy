Checking the Seestar's Status
=============================

seestarpy provides several ways to inspect the current state of your
Seestar — from a quick ASCII dashboard to individual low-level queries.


Status dashboard
----------------

The easiest way to see everything at a glance:

.. code-block:: python

   from seestarpy import status

   status.status_bar()

This prints an ASCII table with the current view state, tracking,
focuser position, filter wheel, plate-solve results, and more.


High-level queries
------------------

.. code-block:: python

   import seestarpy as ssp

   ssp.exposure()             # current exposure time
   ssp.filter_wheel()         # current filter position (1 or 2)
   ssp.focuser()              # current focuser position
   ssp.tracking()             # tracking on/off


Telescope state
---------------

.. code-block:: python

   from seestarpy import raw

   # Overall app / firmware state
   raw.iscope_get_app_state()

   # View and camera state
   raw.get_view_state()
   raw.get_camera_state()

   # Device info and settings
   raw.get_device_state()
   raw.get_setting()


Mount position
--------------

.. code-block:: python

   raw.scope_get_equ_coord()       # current RA/Dec
   raw.scope_get_ra_dec()          # alias
   raw.scope_get_horiz_coord()     # Alt/Az


Tracking and focuser
--------------------

.. code-block:: python

   raw.scope_get_track_state()
   raw.get_focuser_position()
   raw.get_wheel_position()


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
