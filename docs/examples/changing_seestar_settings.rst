Changing the Seestar's settings
===============================

.. note::
    **Assumption**: That you have already set up a connection to the seestar.
    If not, see :doc:`basic_connection`.  All the examples below assume
    ``from seestarpy import raw``.


One dictionary, many settings
-----------------------------

Almost everything configurable about a Seestar lives in a single settings
dictionary.  Read it whole:

.. code-block:: python

    raw.get_setting()["result"]
    # {'temp_unit': 'C', 'exp_ms': {'stack_l': 10000, 'continuous': 500},
    #  'stack_dither': {'pix': 60, 'interval': 5, 'enable': True},
    #  'auto_af': False, 'heater_enable': False, 'focal_pos': 1580, ...}

...and write to it by keyword:

.. code-block:: python

    raw.set_setting(temp_unit="F")
    raw.set_setting(auto_power_off=False)
    raw.set_setting(heater_enable=True)          # dew heater on

Two things to know before you start poking at it.

**Nested settings are replaced, not merged.**  Keys like ``exp_ms``,
``stack_dither`` and ``stack`` hold sub-dictionaries, and the firmware
overwrites the whole block with what you send.  Read the current value,
change one field, send the lot back:

.. code-block:: python

    dither = raw.get_setting()["result"]["stack_dither"]
    dither["interval"] = 6
    raw.set_setting(stack_dither=dither)

This is exactly what the convenience wrappers do for you, which is why
``ssp.dither(every_n_subs=6)`` and ``ssp.exposure(20)`` are the safer way
to touch those two blocks (see :doc:`basic_observing`).

**Settings are persistent and shared.**  They are stored on the scope, not
scoped to your connection, so a change you make here is what the phone app
will see next time it connects — and it stays that way until something
changes it back.

The full list of known keys, with types and defaults, is in the
:func:`~seestarpy.raw.set_setting` API reference.  The most useful ones:

======================  ===================================================
``exp_ms``              sub-exposure lengths — use ``ssp.exposure()``
``stack_dither``        dither throw and cadence — use ``ssp.dither()``
``auto_af``             auto-focus after every goto (default ``False``)
``plan_target_af``      auto-focus between plan targets (default ``False``)
``stack_after_goto``    start stacking as soon as a goto completes
``heater_enable``       dew heater
``auto_power_off``      power down after ~15 min idle (default ``True``)
``expert_mode``         unlocks the 2 s and 5 s sub lengths
``stack_lenhance``      dark subtraction (moves the filter, so call alone)
``beep_volume``         ``'close'`` to silence the scope
``preview``             image/RTSP stream transport, firmware 8.46+
``wide_cam``            use the wide camera (S30 Pro)
======================  ===================================================


Time and location
-----------------

Check if your Seestar has the right time and place:

.. code-block:: python

    raw.pi_get_time()
    raw.get_user_location()

If the returned values indicate that you are Marty McFly and have landed back in
the year your parents were courting, you may want to run the following:

.. code-block:: python

    raw.pi_set_time()
    # For Vienna, Austria
    raw.set_user_location(48.2, 16.4)

Both matter more than they look.  Plate-solving, the Alt/Az conversion, and
the ``start_min`` field of an observation plan are all interpreted against
the scope's own clock and coordinates, so a scope that thinks it is in 1985
will plan a night that never happens.  ``pi_set_time()`` syncs to the clock
and timezone of the machine you are calling from.


Image stream transport (firmware 8.46+)
---------------------------------------

Firmware 8.46 added a ``preview`` settings block that decides how stacked
frames cross the network.  On an 8 MP S30 Pro over Wi-Fi the difference is
twentyfold:

.. code-block:: python

    raw.get_preview_setting()
    # {'image_transfer_mode': 'Raw', 'rtsp_quality': 'HighQuality', ...}
    # None on firmware older than 8.46

    raw.set_image_transfer_mode("Jpg")      # ~2.5 MB per frame, ~5 s
    raw.set_image_transfer_mode("Raw")      # ~50 MB per frame, ~30 s

``'Jpg'`` gives you a finished, firmware-stretched JPEG — ideal for
monitoring.  ``'Raw'`` gives linear 16-bit data, which is what you want if
you intend to process the frames yourself, because the JPEG's tone-mapping
cannot be undone.  Aliases ``'jpeg'``/``'compressed'`` and
``'lossless'``/``'full'`` are accepted and validated before the round-trip.

.. warning::
    This is a persistent device setting shared with the phone app, not a
    per-connection option.  Switching to ``Jpg`` to make a dashboard
    responsive also changes what every other client gets, until you change
    it back.

See :doc:`live_streaming` and :doc:`live_dashboard` for what to do with the
frames once they arrive.


USB-C port: drive or wired LAN
------------------------------

The Seestar's USB-C port is dual-role.  In ``'file'`` mode the scope is a
USB mass-storage **gadget** — plug it into a computer and it mounts as a
drive.  In ``'net'`` mode the scope becomes a USB **host** that drives an
external USB-to-Ethernet adapter, putting it on a wired LAN.

.. code-block:: python

    raw.get_usb_mode()
    # {'typec_mode': 'file', 'usb_en_eth': False}

    raw.set_usb_mode("net")     # arm the scope for a wired LAN
    raw.set_usb_mode("file")    # present the scope as a USB drive

``'file'`` also accepts ``'drive'``, ``'storage'`` and ``'usb'``;
``'net'`` also accepts ``'eth'``, ``'ethernet'`` and ``'lan'``.  The
firmware itself only understands ``'file'`` and ``'net'`` and answers
``code 102`` for anything else, so other spellings are rejected before
they reach the scope.

Two settings are involved — ``typec_mode`` (the port role) and
``usb_en_eth`` (a master switch for USB Ethernet) — and the firmware does
not couple them.  :func:`~seestarpy.raw.set_usb_mode` always writes both,
so the two modes are exact reversals of each other.  If you call
``set_setting`` yourself, remember that writing ``typec_mode`` alone
leaves ``usb_en_eth`` latched at its previous value.

.. note::
    Wired mode needs a **powered** USB-C-to-Ethernet adapter with PD
    between the scope and the router.  A passive cable is not enough:
    ``set_usb_mode("net")`` only arms the firmware.

Switching modes restarts the scope's USB subsystem, so give it a few
seconds to settle; any mounted drive disappears the moment you select
``'net'``.  On an S50 running firmware 8.46 the role change re-negotiated
over an already-seated cable with no replug needed, but other
firmware/host combinations may need the cable physically unplugged and
re-plugged before the drive reappears.

Finding a wired Seestar
~~~~~~~~~~~~~~~~~~~~~~~

A scope in ``'net'`` mode is **dual-homed**: it keeps its Wi-Fi
connection and picks up a second, wired DHCP lease.  Both addresses
answer on port 4700.

The wired address is not reported anywhere in the API — the ``station``
block of :func:`~seestarpy.raw.get_device_state` describes only the Wi-Fi
interface, and there is no ``eth0`` section:

.. code-block:: python

    raw.get_device_state()["result"]["station"]["ip"]
    # '192.168.1.81'   <- the Wi-Fi lease, even when wired

Note that mDNS tends to advertise the *wired* lease, so
:func:`~seestarpy.connection.find_available_ips` may hand you an address
that differs from ``station.ip`` for the same scope.  Both work.  To see
every address a scope answers on, scan port 4700 and compare serial
numbers via :func:`~seestarpy.connection._get_device_id`; a bare socket
probe will not do, because firmware 7.18+ requires an RSA handshake
before it will answer.

.. note::
    A router DHCP reservation is the easiest way to pin a wired scope to
    a fixed address — the firmware exposes no static-IP setting for
    ``eth0``.

