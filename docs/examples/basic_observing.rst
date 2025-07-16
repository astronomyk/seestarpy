Basic commands to start stacking exposures
==========================================

Absolute minimum number of commands to start observing
------------------------------------------------------

Assuming you have already set up your Seestar (see below), these are the minimum
commands needed to get things up and running with ``seestarpy``:

.. code-block:: python

    from seestarpy import raw
    raw.scope_move_to_horizon()
    raw.iscope_start_view(ra=13.4, dec=54.9, target_name="Mizar")
    raw.iscope_start_stack()

Notes:
- ``iscope_start_view`` will trigger a plate-solve action.
- ``iscope_start_stack`` will trigger the create-dark-frame and auto-focus commands

To stop imaging you will need:

.. code-block:: python

    raw.iscope_stop_view("Stack")
    raw.iscope_stop_view(None)
    raw.pi_shutdown(True)       # force=True, to avoid mistakenly calling this

Note:
- ``iscope_stop_view("Stack")`` will gracefully stop the stacking process and
  save both the last frame and the stacked image to disk. It leaves the camera
  on in the ``ContinuousExposure`` viewing mode.
- ``iscope_stop_view(None)`` turns off the camera completely, however it does
  not do anything if the Seestar is currently stacking.


Set up commands
---------------

The basic assumption here is that you have already once connected via the app
to your Seestar and put the Seestar into station mode. Through doing this, it
should already have updated its system time and earth location. You may also
have already set the Seestar to equatorial mode if you plan to mount it on a
wedge.

However if you would like to set these parameters programmatically, here is the
minimal set of commands to do this:

.. code-block:: python

    raw.set_time()
    raw.set_user_location(14.8, 47.9)

    raw.scope_move_to_horizon()
    raw.scope_park(True)        # set_eq_mode=True


More explicit commands
----------------------

Here are a list of more explicit commands that do the individual steps of the
Seestar initialisation workflow:

.. code-block:: python

    raw.scope_move_to_horizon()

    raw.scope_park(set_eq_mode=True)
    raw.scope_move_to_horizon()

    raw.start_create_dark()
    raw.start_auto_focuse()

    raw.get_focuser_position()
    raw.move_focuser(1605)

    raw.scope_get_track_state()
    raw.scope_set_track_state(True)

    raw.iscope_get_app_state()

    raw.scope_goto(12, 88)
    raw.scope_get_equ_coord()

    raw.iscope_start_view()
    raw.get_view_state()

    raw.iscope_start_stack()
    raw.get_view_state()

    raw.iscope_stop_view("Stack")
    raw.iscope_stop_view(None)

