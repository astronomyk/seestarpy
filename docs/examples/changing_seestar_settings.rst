Changing the Seestar's settings
===============================

.. note::
    **Assumption**: That you have already set up a connection to the seestar.
    If not, see :doc:`basic_connection`.


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

