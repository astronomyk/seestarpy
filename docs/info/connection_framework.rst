Connection Framework
====================

This page explains how seestarpy talks to a Seestar under the hood: how a
command is routed to the right telescope, and how the underlying TCP socket
is opened, authenticated, reused and recovered.  Most users never need this
--- :func:`~seestarpy.connection.send_command` and the high-level API "just
work" --- but it matters if you control **multiple Seestars**, run **long
polling loops** (e.g. :func:`~seestarpy.crowdsky.stack_blocks`), or are
debugging connection behaviour.

There are two independent mechanisms: **how the target IP is chosen**
(per-thread routing) and **how the socket is managed** (a persistent,
authenticated connection pool).


The previous model (short-lived sockets)
----------------------------------------

Historically every JSON-RPC command was a complete, throwaway TCP session:

.. code-block:: text

   send_command(params):
       open a brand-new socket to DEFAULT_IP:4700
       if a key is configured: run the full RSA auth handshake
       send the command
       read \r\n frames until the reply id matches (skipping events)
       close the socket

This had two structural problems:

1. **Re-authentication on every call.**  Firmware 7.18+ verifies a client
   *per TCP connection*.  Because each command opened a fresh socket, it
   re-ran the full handshake (``get_verify_str`` -> sign -> ``verify_client``
   -> ``pi_is_verified``, 3 round-trips plus an RSA signature) every single
   time.  A stacking poll loop --- one status query every few seconds for an
   hour --- meant well over a thousand handshakes.

2. **Routing through a mutable global.**  ``send_command`` read the module
   global :data:`~seestarpy.connection.DEFAULT_IP`.  To target a specific
   scope, :func:`~seestarpy.connection.multiple_ips` *reassigned that global*
   inside each worker thread.  With two scopes running in parallel, one
   worker could overwrite the global out from under another --- so a command
   could land on the wrong telescope.


Target resolution: ``current_ip()`` and thread-local routing
------------------------------------------------------------

Routing no longer touches the global.  The target host is resolved at call
time by :func:`~seestarpy.connection.current_ip`:

.. code-block:: python

   _active = threading.local()

   def current_ip():
       return getattr(_active, "ip", None) or DEFAULT_IP

- :data:`~seestarpy.connection.DEFAULT_IP` is still the single-scope default,
  but it is **never mutated for routing** anymore.
- :func:`~seestarpy.connection.multiple_ips` sets ``_active.ip`` on each
  worker **thread**, runs the wrapped function, and clears it afterwards:

  .. code-block:: python

     def call_with_ip(ip):
         _active.ip = ip
         try:
             return func(*args, **kwargs)
         finally:
             _active.ip = None        # don't leak into a reused pool thread

Because :class:`threading.local` is per-thread, two workers targeting
different scopes can never observe each other's IP --- the race is gone by
construction.

**Nested decorated calls inherit the scope.**  When a decorated function is
called *without* an ``ips=`` argument, the wrapper reuses the current
thread's ``_active.ip``.  So ``stack_blocks(ips=2)`` runs on a worker whose
active IP is Seestar 2, and every ``set_batch_stack_setting`` /
``data.list_folder_contents`` it calls internally resolves to that same
Seestar instead of snapping back to :data:`DEFAULT_IP`.

The SMB and HTTP paths follow the same routing: ``data._connect_smb``,
``data._build_http_url`` and ``crowdsky._read_fits_ra_dec`` all resolve their
host via :func:`current_ip` so file listings, downloads and FITS-header reads
address the same Seestar as the JSON-RPC commands.


Socket management: the persistent connection pool
-------------------------------------------------

There is now **one long-lived connection per Seestar IP**, created on first
use and reused thereafter:

.. code-block:: python

   _connections = {}                 # ip -> _Connection
   _connections_lock = threading.Lock()

   def send_command(params):
       return _get_connection(current_ip()).send(params)

Each ``_Connection`` holds:

- ``_sock`` --- the live socket (or ``None`` if not yet/no longer connected),
- ``_buf`` --- a receive buffer that **persists between calls**,
- ``_lock`` --- a per-connection lock, so a single socket is never used by
  two threads at once.

The RSA handshake (firmware 7.18+) runs **once when the socket is opened**,
not once per command.


Anatomy of a ``send_command`` call
----------------------------------

1. :func:`current_ip` picks the target (thread-local override, else
   :data:`DEFAULT_IP`).
2. ``_get_connection(ip)`` returns the pooled ``_Connection`` for that IP,
   creating it once under the pool lock.
3. ``_Connection.send(params)`` acquires the **per-connection lock**, then
   makes up to **two attempts**:

   a. If there is no live socket, ``_connect()`` opens one, applies a 10 s
      timeout, and --- only if a key is configured --- runs the RSA
      handshake **once for the lifetime of this socket**.
   b. The command ``{"id": 1, "verify": true, **params}`` is written, and
      ``\r\n``-terminated frames are read until one carries ``id == 1``.
      Any frame that isn't our reply (the device interleaves ``PiStatus`` /
      ``temp`` events on the same socket) is skipped.  The matched reply dict
      is returned.
4. The parsed JSON-RPC response dict is returned to the caller.

Because ``_buf`` persists, bytes that arrive after a matched reply (typically
the start of an event frame) carry into the next call and are skipped there.
Over a long idle gap the device's events accumulate in the socket buffer and
are drained on the next ``send``.


Reconnect and retry
-------------------

A dropped or half-open socket surfaces as an empty ``recv()`` (raised as
:class:`ConnectionError`) or an :class:`OSError` (including
:class:`socket.timeout`, since the read timeout is 10 s).  ``send`` catches
these, discards the dead socket, and **retries once** --- which reconnects
and re-authenticates on a fresh socket.  If the second attempt also fails it
raises:

.. code-block:: text

   ConnectionError: send_command to <ip> failed after reconnect: <cause>

.. note::

   This is a behavioural change from the old model.  On an unrecoverable
   failure ``send_command`` now **raises** :class:`ConnectionError` rather
   than returning an empty string.  The in-tree callers (which read
   ``.get(...)`` off the response dict) are unaffected, but downstream code
   that silently tolerated an empty return will now see an exception.


Lifecycle and tuning
--------------------

- :func:`~seestarpy.connection.close_connections` closes every pooled socket
  and clears the pool; the next command transparently reconnects.  It is
  registered with :mod:`atexit`, and you can call it yourself to force a
  clean slate (e.g. after changing the auth key, or to release sockets in a
  long-running process).
- :data:`~seestarpy.connection.PERSIST_CONNECTIONS` (default ``True``) is the
  global on/off switch.  Set it to ``False`` to close the socket after every
  command, reproducing the old short-lived-socket behaviour.

  .. code-block:: python

     from seestarpy import connection
     connection.PERSIST_CONNECTIONS = False   # opt back out of pooling


What changed, and the implications
----------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Aspect
     - Previous
     - Current
   * - Sockets
     - New socket per command
     - One reused socket per IP
   * - Auth handshakes
     - Once **per command**
     - Once **per connection**
   * - IP routing
     - Mutated global ``DEFAULT_IP`` (racy)
     - Per-thread ``current_ip()`` (race-free)
   * - Dropped socket
     - n/a (always fresh)
     - Auto-reconnect + retry once
   * - Concurrency to one IP
     - Fully parallel (separate sockets)
     - Serialised by the per-connection lock
   * - Unrecoverable failure
     - Could return ``""``
     - Raises :class:`ConnectionError`

A few consequences worth keeping in mind:

- **Calls to the same Seestar are serialised** by the per-connection lock.
  This is correct --- a single socket cannot safely carry interleaved
  request/reply streams --- and matches the real workload (per-scope work is
  sequential).  **Cross-scope** concurrency is unaffected: different IPs use
  different connections and still run fully in parallel via
  :func:`multiple_ips`.

- **The event listener is independent.**  :mod:`seestarpy.events` keeps its
  own separate connection on port 4700.  The Seestar accepts multiple
  simultaneous TCP connections, so the command pool and the event stream do
  not interfere with each other.

- **Long polling loops are dramatically cheaper.**  A full
  :func:`~seestarpy.crowdsky.stack_blocks` run now authenticates once and
  reuses the socket across every progress poll, instead of opening and
  authenticating a new socket on each poll.
