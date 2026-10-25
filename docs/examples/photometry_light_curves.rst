Photometry and light curves
===========================

Firmware 9.x can measure every star in every frame it stacks, calibrate
the magnitudes against APASS reference stars, and keep a light curve for
the stars you choose.  :mod:`seestarpy.photometry` wraps this.

.. note:: The commands and their JSON keys come from the decompiled
   Seestar app v3.4.1.  The mode switch, reference-star upload and the
   read-only calls were checked against firmware 9.75 on an S50 on
   2026-10-25.  A full night of photometry has not been run through
   seestarpy yet.

1. Switch the stacker to photometry
-----------------------------------

.. code-block:: python

    from seestarpy import photometry, raw

    photometry.set_photometry_mode(True)      # stack.capt_type = "photometry"
    photometry.get_photometry_mode()          # True

The mode is a setting, so it stays on until you switch it back with
``set_photometry_mode(False)``.

2. Go to the target and stack
-----------------------------

.. code-block:: python

    raw.iscope_start_view(ra=20.0133, dec=22.7238, target_name="M 27")
    # ... wait for AutoGoto to finish, then
    raw.iscope_start_stack()

3. Reference stars
------------------

The firmware plate-solves the field and needs APASS reference stars
around it.  A scope on your home network (station mode) with internet
access downloads them itself.  In access-point mode it cannot, and the
official app fills in by downloading them on the phone.  seestarpy does
the same from VizieR:

.. code-block:: python

    photometry.get_check_state()
    # {'has_download_ref_star': False, 'ra_dec_deg_j2000': [300.2, 22.7], ...}

    photometry.provide_reference_stars()      # query APASS + upload

or in two steps, e.g. to change the limits:

.. code-block:: python

    stars = photometry.query_reference_stars(300.2, 22.7,
                                             radius_deg=3.5, mag_limit=10)
    photometry.upload_refstar_info(stars)

4. Look at the measured stars
-----------------------------

.. code-block:: python

    stars = photometry.get_photometry_stars(image_id)["result"]["stars"]
    for s in stars:
        print(s["id"], s["name"], s["measure_mag"], s["err"], s["snr"],
              s["is_reference"], s["is_variable"])

``image_id`` is the ID of a live frame (the ``image_id`` of
:func:`seestarpy.raw.get_annotate_result`).

5. Record light curves
----------------------

.. code-block:: python

    photometry.record_star("123", name="V452 Vul")
    photometry.recorded_stars()

    lc = photometry.light_curve("123")        # sorted by MJD
    photometry.save_light_curve(lc, "v452_vul.csv")

    photometry.stop_recording("123")

Finished recordings are kept on the scope as CSV files:
:func:`~seestarpy.photometry.get_photometry_result` lists them.

The plate solution
------------------

.. code-block:: python

    hdr = photometry.wcs_header(photometry.get_photometry_wcs())

    from astropy.wcs import WCS               # optional
    w = WCS(hdr)

Photometry inside an observation plan
-------------------------------------

Plan targets can run in photometry mode on their own, so a night of
light curves can be scheduled:

.. code-block:: python

    from seestarpy import plan

    p = plan.create_named_plan("Variables", [("V452 Vul", "22:00"),
                                             ("SS Cyg", "00:30")],
                               end_time="03:00")
    plan.configure_plan(p, exposure_ms=20000, capt_type="photometry")
    plan.set_view_plan(p)

See :doc:`observation_plans` for the other per-target settings.
