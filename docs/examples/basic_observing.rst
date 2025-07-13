Basic commands to start stacking exposures
==========================================

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

    raw.scope_goto(12, 88)
    raw.scope_get_equ_coord()

    raw.start_polar_align()

    raw.iscope_start_view()
    raw.get_view_state()

    raw.iscope_start_stack()
    raw.get_view_state()

    raw.iscope_stop_view("Stack")
    raw.iscope_stop_view("ContinuousExposure")

