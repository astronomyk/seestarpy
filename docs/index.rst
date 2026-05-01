.. image:: _static/seestar_py_logo_banner.png
   :alt: SeeStar-Py
   :align: center


Welcome to SeeStar-Py's Documentation!
======================================

.. danger::

   **Firmware 7.18+ requires authentication.**

   Yet again, ZWO is trying to alienate the astro-tinkerer community.

   The reason a lot of us chose the Seestars over the competitor smart-telescopes
   was due to the ability to be able to access and control the seestars in ways
   that ZWO does not offer via their own software. This "open-source" feature
   was one of the **Seestar's greatest USPs** and, if embraced properly, would allow
   **the Seestar user community to leverage their endless creativity to come up
   with project beyond the wildest imagination of the corporate heads at ZWO**.

   Alas, **ZWO's greed is shutting down this effort before it really had a chance
   to grow**, turning what could have been a real game-changer smart-telescope
   into just another piece of consumer electronics that will be surpassed by
   other superior products.

   If your Seestar is running firmware 7.18 or later, seestarpy will not
   be able to connect without a key file.  The ``main``
   branch now ships a built-in extractor: obtain the official ZWO Seestar
   Android APK yourself (e.g. from an APK mirror) and run::

      python -m seestarpy.extract_pem /path/to/Seestar_v3.1.2.apk

   The key is written to ``~/.seestarpy/seestar.pem`` where seestarpy
   auto-discovers it on every connection.  See :doc:`info/authentication`
   for the full setup and the legal basis for interoperability.

.. image:: https://img.shields.io/pypi/v/seestarpy
   :alt: PyPI Version
   :target: https://pypi.org/project/seestarpy/


**seestarpy** is a Python SDK for controlling ZWO Seestar S50 smart
telescopes over your local network.  It wraps the Seestar's JSON-RPC
command interface and binary image streaming protocol into a clean
Python API — no phone app required.


Installation
------------

.. code-block:: bash

   pip install seestarpy

or if you need the dependencies for the PEM extraction:

.. code-block:: bash

   pip install seestarpy[auth]

Getting started
---------------

The shortest path from install to imaging:

.. code-block:: python

   import seestarpy as ssp

   # 1. Connect — the Seestar is auto-discovered via mDNS
   ssp.connection.test_connection()

   # 2. Open the arm
   ssp.open()

   # 3. Goto a target (coordinates resolved automatically)
   ssp.goto_target("M42")

   # 4. Start stacking
   ssp.start_stack()

That's it — the Seestar will slew to M42, plate-solve, and begin
stacking sub-exposures.

To see what the Seestar is currently looking at, grab the latest stacked
frame and pop it up in a matplotlib window:

.. code-block:: python

   from seestarpy import stream

   stream.show_current_stack()              # one Seestar
   stream.show_current_stack(ips="all")     # all Seestars in a subplot grid

If auto-discovery doesn't find your Seestar, set the IP manually:

.. code-block:: python

   ssp.connection.DEFAULT_IP = "192.168.1.246"

You can find your Seestar's IP in the official phone app under the
station-mode settings.


Controlling multiple Seestars
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Most commands accept an ``ips`` keyword to broadcast to multiple
Seestars at once:

.. code-block:: python

   # Discover all Seestars on the network
   ssp.connection.find_available_ips(n_ip=3)

   # Open all arms simultaneously
   ssp.open(ips="all")

   # Goto the same target on all Seestars
   ssp.goto_target("M42", ips="all")

See the :doc:`examples/basic_connection` page for more details.


When you're done
^^^^^^^^^^^^^^^^

.. code-block:: python

   ssp.stop_view()
   ssp.close()


Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   examples/basic_connection
   examples/basic_observing
   examples/basic_status_checks
   examples/changing_seestar_settings
   examples/changing_gain
   examples/observation_plans
   examples/data_management
   examples/live_streaming
   examples/crowdsky_stacking

.. toctree::
   :maxdepth: 2
   :caption: Reference

   info/authentication
   info/errors
   info/image_stream_protocol
   api/api_index


Feedback
--------

Found an issue or have a feature request?
`Open an issue on GitHub <https://github.com/astronomyk/seestarpy/issues>`_.
