Dashboard Module
================

A live web dashboard for every Seestar on the network.  It discovers the
scopes itself, gives each one a card showing its current stacked image
(or the live preview when it isn't stacking) with its status alongside,
and adds or drops cards as scopes come and go.

Start it from the shell:

.. code-block:: bash

   python -m seestarpy.dashboard

or from Python with :func:`~seestarpy.dashboard.server.serve`.

See :doc:`../examples/live_dashboard` for a walkthrough.

Package
-------

.. automodule:: seestarpy.dashboard
    :members:
    :undoc-members:
    :show-inheritance:

Server
------

.. automodule:: seestarpy.dashboard.server
    :members:
    :undoc-members:
    :show-inheritance:

Scope Monitors
--------------

.. automodule:: seestarpy.dashboard.monitor
    :members:
    :undoc-members:
    :show-inheritance:
