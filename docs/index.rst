.. image:: docs/logos/seestar_py_logo_banner.png
   :alt: SeeStar-Py
   :align: center


Welcome to SeeStar-Py's Documentation!
======================================

.. image:: https://img.shields.io/pypi/v/seestarpy
   :alt: PyPI Version
   :target: https://pypi.org/project/seestarpy/

.. image:: https://img.shields.io/pypi/pyversions/seestarpy
   :alt: Supported Python Versions
   :target: https://pypi.org/project/seestarpy/

Description
-----------
**SeeStar-Py** is a Python interface designed for controlling the SeeStar telescope system. It provides utilities for managing connections, data processing, and more — ideal for astronomers and researchers involved with the SeeStar telescope.

Features
--------
- **Connect to SeeStar**: Seamless integration with SeeStar telescope systems.
- **Data Handling**: Tools for processing and transferring observation data.
- **Customizable**: Easily extendable and integrable with other astronomy tools.

Quickstart
----------
Install `seestarpy` using pip:

.. code-block:: bash

   pip install seestarpy

Usage example:

.. code-block:: python

   from seestarpy import connection as conn
   from seestarpy import commands as cmds

   >>> conn.DEFAULT_IP = "192.168.1.243
   >>> cmds.test_connection()




Contents
--------
.. toctree::
   :maxdepth: 2
   :caption: Main Contents

   installation
   usage
   api_reference
   changelog


API Documentation
=================

.. toctree::
  :maxdepth: 2

.. automodule:: your_module_name
  :members:
  :undoc-members:
  :show-inheritance:



Feedback
--------
Found an issue or have a feature request? Please visit our `GitHub Issues page <https://github.com/yourusername/seestarpy/issues>`_.

Enjoy using **seestarpy**!