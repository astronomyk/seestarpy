Connecting to your Seestar
==========================

.. note::
   **Prerequisites:**

   - You are comfortable with Python (scripts, notebooks, or REPL).
   - Your Seestar is in **station mode** and connected to your local
     Wi-Fi network or phone hotspot.
   - Firmware 7.18 and newer needs a signing key on your machine before
     it will answer at all — see :doc:`../info/authentication`.


The short version
-----------------

``import seestarpy`` runs a discovery sweep for you, so in the common case
there is nothing to configure:

.. code-block:: python

   import seestarpy as ssp
   # ✓ Found Seestar S50 at 192.168.1.55 (s50_a3497936)
   # Use connection.AVAILABLE_IPS to get active addresses

   ssp.connection.test_connection()
   # {'jsonrpc': '2.0', 'method': 'test_connection', 'result': 'ok', 'code': 0, ...}

If ``test_connection()`` answers ``'ok'``, you are done — skip to
:doc:`basic_observing`.


How discovery works
-------------------

seestarpy finds scopes the same way the ZWO phone app does: it broadcasts
a ``scan_iscope`` probe over **UDP port 4720**, and every Seestar on the
subnet answers with its **serial number** and model.

.. code-block:: python

   from seestarpy import connection as conn

   conn.discover()
   # ✓ Found Seestar S50 at 192.168.1.55 (s50_a3497936)
   # ✓ Found Seestar S50 at 192.168.1.83 (s50_97783b61)
   # ✓ Found Seestar S30 Pro at 192.168.1.82 (s30pro_ce545589)
   # {'a3497936': '192.168.1.55', '97783b61': '192.168.1.83',
   #  'ce545589': '192.168.1.82'}

Broadcast discovery has two advantages over the ``seestar.local`` mDNS
lookups that older versions of seestarpy used.  It finds **every** scope
in one sweep without you saying how many to look for, and it identifies
them by serial number rather than by hostname — so a scope keeps its
identity when DHCP hands it a new address, or when you move it from Wi-Fi
to a wired connection.

mDNS is still there as a fallback: if nothing answers the broadcast (some
managed switches and guest networks drop broadcast traffic),
:func:`~seestarpy.connection.find_seestar` tries to resolve
``seestar.local`` before giving up.

Two module-level dictionaries hold the results:

.. code-block:: python

   conn.AVAILABLE_IPS
   # {'s50_a3497936': '192.168.1.55', 's50_97783b61': '192.168.1.83'}

   conn.DISCOVERED['a3497936']
   # {'ip': '192.168.1.55', 'sn': 'a3497936', 'model': 'Seestar S50', ...}

:data:`~seestarpy.connection.AVAILABLE_IPS` maps a short *device name*
(model plus serial) to an address, and is what the ``ips=`` keyword
resolves against.  :data:`~seestarpy.connection.DISCOVERED` keeps the full
reply record, keyed by bare serial number.

Re-run ``discover()`` whenever you power a scope on mid-session — nothing
polls the network on your behalf.


Which Seestar am I talking to?
------------------------------

Every command goes to :data:`~seestarpy.connection.DEFAULT_IP` unless you
say otherwise.  Import-time discovery points it at the lowest-numbered
scope found; if nothing was found it falls back to ``"10.0.0.1"``, which
is the address the Seestar uses when it serves its **own** Wi-Fi hotspot
(i.e. you joined the ``S50_xxxxx`` network directly instead of putting the
scope on your LAN).

.. code-block:: python

   conn.DEFAULT_IP
   # '192.168.1.55'

Switch to a different scope without typing addresses:

.. code-block:: python

   conn.set_default_ip(2)              # second scope in serial-number order
   # DEFAULT_IP → 192.168.1.83 (s50_97783b61)

   conn.set_default_ip('ce545589')     # or by serial number
   # DEFAULT_IP → 192.168.1.82 (s30pro_ce545589)

Scope numbers come from :func:`~seestarpy.connection.discovery_order`,
which sorts by serial number.  So "scope 2" is the same physical telescope
tonight as it was last week — unlike IP-ordered numbering, which
reshuffles every time your router renews a lease.


Setting the IP manually
-----------------------

If discovery cannot reach your scope at all (different VLAN, VPN, port
forwarding), set the address yourself.  You will find it in the official
phone app under the station-mode / advanced settings.

.. code-block:: python

   import seestarpy as ssp

   ssp.connection.DEFAULT_IP = "192.168.1.246"
   ssp.connection.test_connection()

That covers a single scope.  For multi-scope addressing as well, fill
``AVAILABLE_IPS`` by hand — the names are yours to choose:

.. code-block:: python

   ssp.connection.AVAILABLE_IPS = {
       "living_room": "192.168.1.246",
       "balcony": "192.168.1.83",
   }
   ssp.open(ips="balcony")


Talking to several Seestars at once
-----------------------------------

Nearly every function in seestarpy accepts an ``ips=`` keyword.  The call
is fanned out to each address on its own thread, so three scopes take no
longer than one:

.. code-block:: python

   conn.discover()

   ssp.open(ips="all")                 # every discovered scope
   ssp.goto_target("M42", ips="all")

   ssp.exposure(20, ips=[1, 3])        # first and third scope only
   ssp.exposure(ips='s50_a3497936')    # one scope, by device name

``ips=`` accepts any of these, or a list mixing them:

===========================  ==================================================
``None`` (the default)       the current ``DEFAULT_IP``
``"all"``                    every entry in ``AVAILABLE_IPS``
an ``int``                   1-based scope number in serial-number order
``'a3497936'``               a bare serial number
``'s50_a3497936'``           a device name, as printed by ``discover()``
``'192.168.1.55'``           a literal address or hostname
===========================  ==================================================

The return value depends on how many scopes you addressed: a single scope
returns the reply itself, several return a ``{ip: reply}`` dictionary.

.. code-block:: python

   ssp.exposure()                      # {'stack_l': 10000, 'continuous': 500}
   ssp.exposure(ips="all")             # {'192.168.1.55': {...}, '192.168.1.83': {...}}

.. warning::
   Entries that cannot be resolved are dropped with a printed warning
   rather than raising.  If you typo a serial number the command still
   runs — just on fewer scopes than you meant.  Count the entries in the
   returned dictionary when that matters.


Under the hood
--------------

Commands are JSON-RPC messages on **port 4700**, and seestarpy keeps one
authenticated connection open per scope rather than reconnecting for every
call — the firmware 7.18+ RSA handshake makes reconnecting expensive.

.. code-block:: python

   conn.PERSIST_CONNECTIONS = False    # revert to a fresh socket per command
   conn.close_connections()            # drop the pool; the next call reconnects

Pooled connections are closed when the interpreter exits, so you do not
normally need to call ``close_connections()`` yourself.

To watch the traffic — useful when a command does something you did not
expect:

.. code-block:: python

   conn.VERBOSE_LEVEL = 2              # 0 = silent, 1 = default, 2 = chatty

For the full protocol story — framing, authentication, error codes — see
:doc:`../info/connection_framework`.


Opening and closing
-------------------

Before slewing to a target, the arm must be raised out of its parked
position:

.. code-block:: python

   ssp.open()           # raise the arm to horizontal

When you're done for the night:

.. code-block:: python

   ssp.stop_view()      # stop imaging and shut the camera down
   ssp.close()          # park the arm

Both take ``ips=`` too, so a three-scope shutdown is two lines:

.. code-block:: python

   ssp.stop_view(ips="all")
   ssp.close(ips="all")
