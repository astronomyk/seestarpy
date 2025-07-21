![SeeStar-Py](docs/_static/seestar_py_logo_banner.png)
A light-weight python module to drive the Seestar smart telescopes

This package is on ReadTheDocs. See [seestarpy.readthedocs.io](https://seestarpy.readthedocs.io/en/latest/)


Quickstart
----------
Install `seestarpy` using pip:

    $ pip install seestarpy

Usage example:

    from seestarpy import connection as conn
    from seestarpy import raw
        
    conn.DEFAULT_IP = "192.168.1.243"                # NOTE - set your own IP address! This is mine.
    raw.test_connection()                            # Test if the seestar is connected to the wifi in station mode

    raw.scope_move_to_horizon()                      # Turn on telescope
    raw.iscope_start_view(ra=13.4, dec=54.9, target_name="Mizar")  # Move to target and turn on camera
    raw.iscope_start_stack()                         # Start stacking sub-frames   

    raw.iscope_stop_view("Stack")                    # Turn off frame stacking
    raw.iscope_stop_view("ContinuousExposure")       # Turn off camera
    raw.pi_shutdown(True)                            # force=True to avoid mistakenly shutting down 
