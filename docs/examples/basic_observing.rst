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


Using explicit coordinates
--------------------------

If you prefer to specify coordinates yourself, or are working offline:

.. code-block:: python

   ssp.goto_target("Mizar", ra=13.4, dec=54.9)

RA is in decimal hours [0, 24) and Dec is in decimal degrees [-90, 90].


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


Stopping and parking
--------------------

.. code-block:: python

   # Stop stacking (saves the last frame and stacked image)
   ssp.raw.iscope_stop_view("Stack")

   # Turn off the camera completely
   ssp.stop_view()

   # Park the arm
   ssp.close()

   # Or shut down the Seestar entirely
   ssp.raw.pi_shutdown(True)       # force=True to confirm


Initial setup commands
----------------------

The first time you use seestarpy (or after a firmware update), you may
need to sync the Seestar's clock and location:

.. code-block:: python

   ssp.raw.pi_set_time()
   ssp.raw.set_user_location(lat=48.2, long=16.4)    # Vienna, Austria

If you use an equatorial wedge:

.. code-block:: python

   ssp.set_eq_mode(True)      # park into EQ mode
   ssp.open()                 # raise the arm again


Exposure and focus
------------------

.. code-block:: python

   ssp.exposure()                   # read current exposure time
   ssp.exposure(10)                 # set to 10 seconds
   ssp.exposure(30, which="stack_l")

   ssp.focuser()                    # read current focuser position
   ssp.focuser("auto")              # run auto-focus
   ssp.focuser(pos=1605)            # set manual position


Low-level commands
------------------

The ``raw`` module gives direct access to every JSON-RPC command the
Seestar supports.  The high-level functions above are wrappers around
these:

.. code-block:: python

   from seestarpy import raw

   raw.scope_move_to_horizon()
   raw.iscope_start_view(ra=13.4, dec=54.9, target_name="Mizar")
   raw.iscope_start_stack()
   raw.scope_goto(12, 88)
   raw.scope_get_equ_coord()

See the :doc:`../api/raw` API reference for the full list.
