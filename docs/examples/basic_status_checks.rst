Checking the Status of the Seestar
==================================

.. code-block:: python

    from seestarpy import raw

    raw.iscope_get_app_state()
    raw.get_view_state()
    raw.get_camera_state()

    raw.get_device_state()
    raw.get_setting()

    raw.scope_get_track_state()
    raw.get_focuser_position()
    raw.set_wheel_position()

    raw.scope_get_horiz_coord()
    raw.scope_get_equ_coord()
    raw.scope_get_ra_dec()

