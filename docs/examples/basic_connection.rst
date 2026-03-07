Connecting to your Seestar
==========================

.. note::
   **Prerequisites:**

   - You are comfortable with Python (scripts, notebooks, or REPL).
   - Your Seestar is in **station mode** and connected to your local
     Wi-Fi network or phone hotspot.


Auto-discovery (mDNS)
---------------------

By default seestarpy discovers your Seestar automatically via mDNS
(``seestar.local``).  Just import and go:

.. code-block:: python

   import seestarpy as ssp

   ssp.connection.test_connection()
   # {'method': 'test_connection', 'result': 'ok', ...}

If auto-discovery works, you don't need to set an IP at all.


Setting the IP manually
-----------------------

If mDNS doesn't work on your network (some routers block it), set
the IP address explicitly.  You can find it in the official Seestar
phone app under the station-mode / advanced settings.

.. code-block:: python

   import seestarpy as ssp

   ssp.connection.DEFAULT_IP = "192.168.1.246"
   ssp.connection.test_connection()


Multiple Seestars
-----------------

If you have more than one Seestar on the network, use
:func:`~seestarpy.connection.find_available_ips` to discover them:

.. code-block:: python

   ssp.connection.find_available_ips(n_ip=3)

This populates the internal IP list.  You can then send commands to
all discovered Seestars with ``ips="all"``, or to specific ones:

.. code-block:: python

   ssp.open(ips="all")                   # open all arms
   ssp.goto_target("M42", ips="all")     # all goto M42
   ssp.goto_target("M31", ips=1)         # only Seestar #1


Opening and closing
-------------------

Before slewing to a target, the arm must be raised:

.. code-block:: python

   ssp.open()           # raise the arm to horizontal

When you're done for the night:

.. code-block:: python

   ssp.stop_view()      # stop imaging
   ssp.close()          # park the arm
