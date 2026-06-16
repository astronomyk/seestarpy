import atexit
import json
import socket
import threading
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError

VERBOSE_LEVEL = 1
DEFAULT_PORT = 4700

# Reuse one authenticated TCP connection per Seestar instead of opening a
# fresh socket (and re-running the RSA auth handshake) on every command.
# Set to False to fall back to the old short-lived-socket behaviour.
PERSIST_CONNECTIONS = True


def find_seestar():
    """
    Find a Seestar on the local network using mDNS hostname resolution.

    Attempts to resolve ``seestar.local`` via DNS.  This function is called
    automatically when the ``seestarpy`` package is imported, and its result
    is used to set :data:`DEFAULT_IP`.

    If the Seestar is not found (e.g. you are connected to a different
    network), :data:`DEFAULT_IP` falls back to ``"10.0.0.1"`` — the
    Seestar's own Wi-Fi hotspot address.

    Returns
    -------
    str or None
        The IP address of the Seestar if found, otherwise ``None``.

    Examples
    --------

        >>> from seestarpy import connection as conn
        >>> conn.find_seestar()
        Seestar found at: 192.168.1.243
        '192.168.1.243'

    """
    try:
        ip = socket.gethostbyname('seestar.local')
        print(f"Seestar found at: {ip}")
        return ip
    except socket.gaierror:
        print("Seestar not found on network")
        return None


seestar_ip = find_seestar()
DEFAULT_IP = seestar_ip if seestar_ip else "10.0.0.1"
AVAILABLE_IPS = {'seestar.local': DEFAULT_IP}

# Per-thread "active" target IP.  :func:`multiple_ips` sets this on each
# worker thread so concurrent broadcasts to different scopes don't race on a
# shared global, and nested decorated calls inherit the right scope.
_active = threading.local()


def current_ip():
    """Return the IP the current call should target.

    Resolution order:

    1. the per-thread active IP set by :func:`multiple_ips` (if any), then
    2. the module-level :data:`DEFAULT_IP`.

    Always use this (not :data:`DEFAULT_IP` directly) when resolving the
    target host at call time, so multi-Seestar broadcasts stay correct.
    """
    return getattr(_active, "ip", None) or DEFAULT_IP


def resolve_ips(call_time_ips):
    """Resolve the ``ips=`` kwarg to a flat list of IP-address strings.

    Accepts the same shapes as :func:`multiple_ips`: ``None`` (current
    :data:`DEFAULT_IP`), an int (``2`` → ``seestar-2.local``), a hostname
    or IP string, the literal ``"all"``, or a list mixing any of these.
    Unknown entries are dropped (with a warning printed) so the result
    is always a non-empty list of resolved IPs when input is valid.
    """
    def _resolve(ip):
        if isinstance(ip, list):
            return [_resolve(i) for i in ip]
        elif isinstance(ip, str):
            if ip in AVAILABLE_IPS:
                return AVAILABLE_IPS[ip]
            elif ip in AVAILABLE_IPS.values():
                return ip
            else:
                print(f"{ip} is not a valid IP address")
                return None
        elif isinstance(ip, int):
            name = f"seestar-{ip}.local" if ip > 1 else "seestar.local"
            return _resolve(name)
        elif ip is None:
            return DEFAULT_IP

    if isinstance(call_time_ips, str) and call_time_ips.lower() == "all":
        call_time_ips = list(AVAILABLE_IPS.values())
    if not isinstance(call_time_ips, list):
        call_time_ips = [call_time_ips]
    resolved = _resolve(call_time_ips)
    return [ip for ip in resolved if ip is not None]


def multiple_ips(func):
    """
    Decorator that allows a function to run against multiple IP addresses.
    Pass `ips` at call time to override DEFAULT_IP.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract the ips list from call arguments.  When the caller doesn't
        # pass ips=, inherit an active nested scope (set by an outer
        # @multiple_ips worker) so the call doesn't snap back to DEFAULT_IP.
        # If there's no active scope, leave it as None so resolve_ips applies
        # the DEFAULT_IP special-case (unvalidated) exactly as before.
        call_time_ips = kwargs.pop('ips', None)
        if call_time_ips is None:
            active = getattr(_active, "ip", None)
            if active is not None:
                call_time_ips = active
        ips = resolve_ips(call_time_ips)

        def call_with_ip(ip):
            """Run the wrapped function with *ip* as the thread-local target."""
            _active.ip = ip
            try:
                if VERBOSE_LEVEL >= 1:
                    print(f"{func.__name__}: call to {ip}")
                return func(*args, **kwargs)
            finally:
                # Clear so a pooled/reused worker thread doesn't leak the IP.
                _active.ip = None

        results = {}
        with ThreadPoolExecutor(max_workers=len(ips)) as executor:
            future_to_ip = {executor.submit(call_with_ip, ip): ip for ip in ips}
            for future in future_to_ip:
                ip = future_to_ip[future]
                results[ip] = future.result()

        # Return single result if only one IP, otherwise return dict keyed by IP
        return list(results.values())[0] if len(results) == 1 else results

    return wrapper


def find_available_ips(n_ip, timeout=2):
    """
    Find all Seestars on the local network using parallel mDNS lookups.

    Resolves hostnames ``seestar.local``, ``seestar-2.local``, …,
    ``seestar-<n_ip>.local`` in parallel and updates the module-level
    :data:`AVAILABLE_IPS` dictionary with the results.  Use this when
    controlling multiple Seestars from a single script.

    Parameters
    ----------
    n_ip : int
        Maximum Seestar index to search for.  For example, ``n_ip=3``
        will probe ``seestar.local``, ``seestar-2.local``, and
        ``seestar-3.local``.
    timeout : float, optional
        Maximum time in seconds to wait for all lookups.  Default is 2.

    Examples
    --------

        >>> from seestarpy import connection as conn
        >>> conn.find_available_ips(3)
        ✓ Found seestar.local at 192.168.1.243
        ✓ Found seestar-2.local at 192.168.1.244
        ✗ seestar-3.local has no active IP address
        Use connection.AVAILABLE_IPS to get active addresses
        >>> conn.AVAILABLE_IPS
        {'seestar.local': '192.168.1.243', 'seestar-2.local': '192.168.1.244'}

    """
    hostnames = ['seestar.local'] + [f'seestar-{i}.local' for i in
                                     range(2, n_ip + 1)]
    found = {}

    def try_lookup(hostname):
        try:
            ip = socket.gethostbyname(hostname)
            return (hostname, ip)
        except socket.gaierror:
            return None

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(try_lookup, h): h for h in hostnames}

    try:
        for future in as_completed(futures, timeout=timeout):
            result = future.result()
            if result:
                name, ip = result
                found[name] = ip
                print(f"✓ Found {name} at {ip}")
    except FuturesTimeoutError:
        pass

    for hostname in hostnames:
        if hostname not in found:
            print(f"✗ {hostname} has no active IP address")

    print("Use connection.AVAILABLE_IPS to get active addresses")
    AVAILABLE_IPS.update(found)


def set_default_ip(n):
    """
    Set :data:`DEFAULT_IP` to the *n*-th Seestar in :data:`AVAILABLE_IPS`.

    This is a convenience shorthand so you can switch between Seestars
    with a single integer instead of typing full hostnames or IPs.

    The mapping follows the Seestar naming convention:

    - ``1`` → ``seestar.local``
    - ``2`` → ``seestar-2.local``
    - ``3`` → ``seestar-3.local``
    - etc.

    Parameters
    ----------
    n : int
        Seestar number (1-based).

    Raises
    ------
    KeyError
        If the corresponding hostname is not in :data:`AVAILABLE_IPS`.
        Call :func:`find_available_ips` first to populate the dictionary.

    Examples
    --------
    ::

        >>> from seestarpy import connection as conn
        >>> conn.find_available_ips(3)
        >>> conn.set_default_ip(2)
        DEFAULT_IP → 192.168.1.83 (seestar-2.local)

    """
    global DEFAULT_IP
    hostname = f"seestar-{n}.local" if n > 1 else "seestar.local"
    if hostname not in AVAILABLE_IPS:
        raise KeyError(
            f"{hostname} not found in AVAILABLE_IPS. "
            f"Call find_available_ips() first. "
            f"Available: {list(AVAILABLE_IPS.keys())}"
        )
    DEFAULT_IP = AVAILABLE_IPS[hostname]
    print(f"DEFAULT_IP \u2192 {DEFAULT_IP} ({hostname})")


class _Connection:
    """A persistent, authenticated JSON-RPC connection to one Seestar.

    The socket is opened and the firmware 7.18+ RSA handshake is run once,
    then reused across commands so a long polling loop doesn't re-pay the
    handshake (~3 round-trips + a signature) on every call.  If the socket
    drops, the next :meth:`send` reconnects, re-authenticates and retries
    once.  All access is serialised by a per-connection lock so one socket
    is never used by two threads at once.
    """

    _READ_TIMEOUT = 10

    def __init__(self, ip, port=DEFAULT_PORT):
        self.ip = ip
        self.port = port
        self._sock = None
        self._buf = ""
        self._lock = threading.Lock()

    # -- socket lifecycle ---------------------------------------------------
    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self._READ_TIMEOUT)
        s.connect((self.ip, self.port))
        # Authenticate if a key is configured (firmware 7.18+).
        from .auth import authenticate, KEY_PATH as _AUTH_KEY
        if _AUTH_KEY is not None:
            authenticate(s)
        self._sock = s
        self._buf = ""

    def _close_locked(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._buf = ""

    def close(self):
        with self._lock:
            self._close_locked()

    # -- one request/reply round on the live socket -------------------------
    def _send_once(self, cmd, cmd_id):
        message = json.dumps(cmd) + "\r\n"
        if VERBOSE_LEVEL >= 1:
            print(f"\nSending: {message.strip()}")
        self._sock.sendall(message.encode())

        # Read frames until the one matching cmd_id.  The Seestar interleaves
        # unsolicited events ("Event":"PiStatus", "temp", ...) onto the same
        # socket, so skip anything that isn't our reply.
        while True:
            while "\r\n" not in self._buf:
                chunk = self._sock.recv(4096).decode("utf-8")
                if not chunk:
                    # Peer closed the connection — signal a reconnect.
                    raise ConnectionError("Seestar closed the connection")
                self._buf += chunk
            line, self._buf = self._buf.split("\r\n", 1)
            if not line:
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(frame, dict) and frame.get("id") == cmd_id:
                return frame
            if VERBOSE_LEVEL >= 2:
                ev = frame.get("Event") or frame.get("method") \
                    if isinstance(frame, dict) else None
                print(f"  (skipped event: {ev})")

    def send(self, params):
        cmd_id = 1
        cmd = {"id": cmd_id, "verify": True}
        cmd.update(params)

        with self._lock:
            last_exc = None
            for attempt in (1, 2):
                try:
                    if self._sock is None:
                        self._connect()
                    parsed = self._send_once(cmd, cmd_id)
                    if not PERSIST_CONNECTIONS:
                        self._close_locked()
                    if VERBOSE_LEVEL >= 1:
                        print(f"\nRecieved: {json.dumps(parsed)}")
                    if VERBOSE_LEVEL >= 2:
                        print("\n✅ Response:")
                        print(f"  method: {parsed.get('method')}")
                        print(f"  result: {json.dumps(parsed.get('result'), indent=2)}")
                        print(f"  code  : {parsed.get('code')}")
                        print(f"  error : {parsed.get('error')}")
                    return parsed
                except (OSError, ConnectionError) as exc:
                    # Socket dropped (or timed out) — discard it and, on the
                    # first attempt, reconnect + re-authenticate and retry.
                    last_exc = exc
                    self._close_locked()
                    if VERBOSE_LEVEL >= 1 and attempt == 1:
                        print(f"  (connection to {self.ip} dropped: {exc} — "
                              f"reconnecting)")
            raise ConnectionError(
                f"send_command to {self.ip} failed after reconnect: {last_exc}"
            )


# Pool of persistent connections keyed by IP.
_connections = {}
_connections_lock = threading.Lock()


def _get_connection(ip):
    """Return the (lazily created) :class:`_Connection` for *ip*."""
    with _connections_lock:
        conn = _connections.get(ip)
        if conn is None:
            conn = _Connection(ip)
            _connections[ip] = conn
        return conn


def close_connections():
    """Close and discard all pooled Seestar connections.

    Safe to call anytime; the next :func:`send_command` transparently
    reconnects.  Registered to run at interpreter exit.
    """
    with _connections_lock:
        for conn in _connections.values():
            conn.close()
        _connections.clear()


atexit.register(close_connections)


def send_command(params):
    """
    Send a JSON-RPC command to the Seestar over TCP.

    Sends the JSON payload to the current target (see :func:`current_ip`) on
    port :data:`DEFAULT_PORT` over a persistent, authenticated connection
    (reused across calls; see :data:`PERSIST_CONNECTIONS`) and waits for the
    ``\\r\\n``-terminated reply whose ``id`` matches, skipping any
    unsolicited events the device interleaves on the socket.

    Most users will not call this directly — use the functions in
    :mod:`seestarpy.raw` or the top-level convenience API instead.

    Parameters
    ----------
    params : dict
        A dictionary with at least a ``"method"`` key.  An optional
        ``"params"`` key provides method-specific arguments.
        For example: ``{"method": "scope_park", "params": {"equ_mode": True}}``.

    Returns
    -------
    dict
        The parsed JSON-RPC response dictionary with keys ``'jsonrpc'``,
        ``'Timestamp'``, ``'method'``, ``'result'``, ``'code'``, and ``'id'``.

    Raises
    ------
    ConnectionError
        If the command could not be delivered and answered even after one
        reconnect attempt.

    Examples
    --------

        >>> from seestarpy.connection import send_command
        >>> send_command({"method": "test_connection"})
        {'jsonrpc': '2.0', 'Timestamp': '...', 'method': 'test_connection',
         'result': 'ok', 'code': 0, 'id': 1}

    """
    return _get_connection(current_ip()).send(params)
