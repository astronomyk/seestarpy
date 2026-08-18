"""Live web dashboard for every Seestar on the network.

Discovers all reachable Seestars (UDP broadcast, see
:func:`seestarpy.connection.discover`), opens an event connection and an
image stream to each one, and serves a page with one card per scope: the
current stacked image — or the live preview when the scope isn't
stacking — with its status listed alongside.

Cards are created and removed on their own as scopes are switched on and
off, so nothing needs restarting mid-session.

Quick start
-----------

From the shell::

    python -m seestarpy.dashboard

From Python::

    >>> from seestarpy import dashboard
    >>> dashboard.serve()                      # blocks until Ctrl-C

Keep control of the interpreter::

    >>> server = dashboard.serve(block=False, open_browser=False)
    >>> server.url
    'http://192.168.1.20:8080/'
    >>> server.stop()

Requirements
------------

Decoding the Seestar's binary image stream needs NumPy and Pillow::

    pip install 'seestarpy[dashboard]'

Without them the status half of every card still works; the image panel
reports the missing dependency.
"""

from .monitor import Fleet, ScopeMonitor, encode_frame
from .server import DashboardServer, serve

__all__ = [
    "serve",
    "DashboardServer",
    "Fleet",
    "ScopeMonitor",
    "encode_frame",
]
