.. image:: _static/seestar_py_logo_banner.png
   :alt: SeeStar-Py
   :align: center


Welcome to SeeStar-Py's Documentation!
======================================

.. image:: https://img.shields.io/pypi/v/seestarpy
   :alt: PyPI Version
   :target: https://pypi.org/project/seestarpy/


Description
-----------
**SeeStar-Py** is a light-weight Python interface designed for controlling the
SeeStar telescope system.

.. warning:: 2025-07-13 :
   This is the first push of seestar-py to pypi and rtd. Things could change rapidly, bigly, and without warning.

Quickstart
----------
Install ``seestarpy`` using pip:

.. code-block:: bash

   pip install seestarpy

Usage example:

.. code-block:: python

   from seestarpy import connection as conn
   from seestarpy import raw

   # replace this with the IP of your Seestar
   conn.DEFAULT_IP = "192.168.1.243"
   raw.test_connection()


Contents
--------
.. toctree::
   :maxdepth: 2
   :caption: Main Contents

   examples/basic_connection
   examples/basic_observing
   examples/basic_status_checks
   examples/changing_seestar_settings
   examples/changing_gain
   examples/live_streaming
   examples/observation_plans
   info/errors
   info/image_stream_protocol
   api/api_index


Feedback
--------
Found an issue or have a feature request?
`GitHub Issues page <https://github.com/yourusername/seestarpy/issues>`_.

Enjoy (good luck) using ``seestarpy``!