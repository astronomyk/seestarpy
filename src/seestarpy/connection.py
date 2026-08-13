import atexit
import json
import socket
import threading
import time
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError

VERBOSE_LEVEL = 1
DEFAULT_PORT = 4700

# UDP broadcast discovery — the mechanism the ZWO app itself uses.  Every
# Seestar listens on this port and answers a ``scan_iscope`` probe with its
# serial number, model and (implicitly) its current IP.  Scopes are therefore
# identified by *serial number*, not by hostname, which is what keeps
# discovery working when a scope moves between Wi-Fi and a wired switch and
# picks up a different address.
DISCOVERY_PORT = 4720
DISCOVERY_TIMEOUT = 2.0     # seconds to listen for replies
DISCOVERY_INTERVAL = 0.5    # seconds between repeat probes inside that window

# Reuse one authenticated TCP connection per Seestar instead of opening a
# fresh socket (and re-running the RSA auth handshake) on every command.
# Set to False to fall back to the old short-lived-socket behaviour.
PERSIST_CONNECTIONS = True

# Serial number -> full discovery record, filled by :func:`discover`.
DISCOVERED = {}

# Short device name -> IP, e.g. ``{'s50_a3497936': '192.168.1.55'}``.  Filled
# by :func:`discover`; the legacy mDNS path (:func:`find_available_ips` with
# ``mdns=True``) instead adds ``seestar-N.local`` keys.  One entry per scope.
AVAILABLE_IPS = {}

# Replaced at the bottom of the module by the import-time discovery sweep.
DEFAULT_IP = "10.0.0.1"


def _dev_id(model, sn):
    """Condense a model + serial into the short ``s50_a3497936`` form."""
    model = (model or "").replace("Seestar", "").replace(" ", "").lower()
    sn = sn or ""
    return f"{model}_{sn}" if model and sn else (model or sn or None)


def _local_broadcast_addresses():
    """Return the IPv4 broadcast addresses to send discovery probes to.

    Every local IPv4 address contributes its ``x.y.z.255`` directed
    broadcast (a /24 is assumed — Seestars live on ordinary home subnets),
    and the limited broadcast ``255.255.255.255`` is appended as a fallback.
    Directed addresses come first and matter most: on a multi-homed host
    (VPN, WSL, Hyper-V) the limited broadcast frequently leaves through the
    wrong interface and reaches nothing.
    """
    ips = set()
    try:
        for _, _, _, _, sa in socket.getaddrinfo(socket.gethostname(), None,
                                                 socket.AF_INET):
            ips.add(sa[0])
    except socket.gaierror:
        pass
    # The interface that would carry a default-route packet — catches the
    # common case where gethostname() resolves to something useless.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ips.add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    targets = []
    for ip in sorted(ips):
        if ip.startswith("127."):
            continue
        directed = ".".join(ip.split(".")[:3]) + ".255"
        if directed not in targets:
            targets.append(directed)
    targets.append("255.255.255.255")
    return targets


def _parse_scan_reply(data, ip):
    """Turn one ``scan_iscope`` datagram into a discovery record, or None."""
    try:
        msg = json.loads(data.decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict):
        return None
    result = msg.get("result") or {}
    sn = result.get("sn")
    if not sn:
        return None
    model = result.get("product_model") or result.get("model") or ""
    return {
        "sn": sn,
        "ip": ip,
        "model": model,
        "dev_id": _dev_id(model, sn),
        "ssid": result.get("ssid"),
        "tcp_clients": result.get("tcp_client_num"),
        "connect_lock": result.get("connect_lock"),
        "verified": result.get("is_verified"),
    }


def discover(timeout=None, port=None, update=True, quiet=False):
    """
    Find every Seestar on the local network by UDP broadcast.

    Broadcasts the firmware's own discovery probe —
    ``{"id": 1, "method": "scan_iscope", "params": ""}`` on UDP port
    :data:`DISCOVERY_PORT` — and collects the replies, which carry each
    scope's serial number and model.  The probe is repeated every
    :data:`DISCOVERY_INTERVAL` seconds for the whole listening window, so a
    single dropped datagram doesn't lose a scope.

    This is what the ZWO phone app does, and unlike the older
    ``seestar-N.local`` hostname lookups it does not depend on mDNS being
    forwarded across the network — so it keeps working when scopes move
    between Wi-Fi and a wired switch.

    Parameters
    ----------
    timeout : float, optional
        Seconds to listen for replies.  Defaults to
        :data:`DISCOVERY_TIMEOUT` (2 s); replies normally arrive within
        ~150 ms, so the rest of the window is just insurance.
    port : int, optional
        UDP port to probe.  Defaults to :data:`DISCOVERY_PORT` (4720).
    update : bool, optional
        Update the module-level :data:`DISCOVERED` and
        :data:`AVAILABLE_IPS` dictionaries with the results.  Default True.
    quiet : bool, optional
        Suppress the printed summary.  Default False.

    Returns
    -------
    dict
        ``{serial_number: ip}`` for every scope that answered.

    Examples
    --------

        >>> from seestarpy import connection as conn
        >>> conn.discover()
        ✓ Found Seestar S50 at 192.168.1.55 (s50_a3497936)
        ✓ Found Seestar S50 at 192.168.1.83 (s50_97783b61)
        ✓ Found Seestar S30 Pro at 192.168.1.82 (s30pro_ce545589)
        Use connection.AVAILABLE_IPS to get active addresses
        {'a3497936': '192.168.1.55', '97783b61': '192.168.1.83',
         'ce545589': '192.168.1.82'}

    """
    timeout = DISCOVERY_TIMEOUT if timeout is None else timeout
    port = DISCOVERY_PORT if port is None else port
    probe = json.dumps({"id": 1, "method": "scan_iscope",
                        "params": ""}).encode() + b"\n\n"
    targets = _local_broadcast_addresses()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.15)

    found = {}
    try:
        deadline = time.monotonic() + timeout
        next_probe = 0.0
        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            if now >= next_probe:
                for target in targets:
                    try:
                        sock.sendto(probe, (target, port))
                    except OSError:
                        # A dead/blocked interface shouldn't abort the sweep.
                        pass
                next_probe = now + DISCOVERY_INTERVAL
            try:
                data, addr = sock.recvfrom(4096)
            except (socket.timeout, OSError):
                continue
            record = _parse_scan_reply(data, addr[0])
            if record:
                # Last reply wins: a scope that just changed address answers
                # from its new IP, and that's the one worth keeping.
                found[record["sn"]] = record
    finally:
        sock.close()

    if update:
        DISCOVERED.update(found)
        for record in found.values():
            AVAILABLE_IPS[record["dev_id"]] = record["ip"]
            # Discovery already told us model + serial, so the device-id
            # cache can skip its get_device_state round-trip later on.
            _device_ids[record["ip"]] = record["dev_id"]

    if not quiet:
        if found:
            for sn in sorted(found):
                rec = found[sn]
                model = rec["model"] or "Seestar"
                print(f"✓ Found {model} at {rec['ip']} ({rec['dev_id']})")
            print("Use connection.AVAILABLE_IPS to get active addresses")
        else:
            print("✗ No Seestars answered the UDP discovery probe "
                  f"(port {port})")

    return {sn: rec["ip"] for sn, rec in found.items()}


def find_seestar():
    """
    Find a single Seestar on the local network.

    Runs a UDP broadcast sweep (:func:`discover`) and returns the address of
    the first scope found, ordered by serial number.  If nothing answers the
    broadcast — some managed switches and guest networks drop it — falls
    back to resolving ``seestar.local`` via mDNS.

    This function is called automatically when the ``seestarpy`` package is
    imported, and its result is used to set :data:`DEFAULT_IP`.  If no
    Seestar is found at all, :data:`DEFAULT_IP` falls back to ``"10.0.0.1"``
    — the Seestar's own Wi-Fi hotspot address.

    Returns
    -------
    str or None
        The IP address of the Seestar if found, otherwise ``None``.

    Examples
    --------

        >>> from seestarpy import connection as conn
        >>> conn.find_seestar()
        ✓ Found Seestar S50 at 192.168.1.55 (s50_a3497936)
        Use connection.AVAILABLE_IPS to get active addresses
        '192.168.1.55'

    """
    found = discover()
    if found:
        return found[sorted(found)[0]]

    try:
        ip = socket.gethostbyname('seestar.local')
    except socket.gaierror:
        print("Seestar not found on network")
        return None

    dev_id = _get_device_id(ip)
    AVAILABLE_IPS['seestar.local'] = ip
    suffix = f" ({dev_id})" if dev_id else ""
    print(f"Seestar found via mDNS at: {ip}{suffix}")
    return ip


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


def discovery_order():
    """Serial numbers of all discovered Seestars, in scope-number order.

    Sorted by serial number, so scope ``1``, ``2``, ``3`` … mean the same
    physical telescope from run to run and from network to network — unlike
    an IP-ordered list, which reshuffles whenever DHCP does.
    """
    return sorted(DISCOVERED)


def _nth_scope(n):
    """Map a 1-based scope number onto a key :func:`resolve_ips` understands.

    A ``seestar-N.local`` hostname wins if one was registered (the legacy
    mDNS path), otherwise the *n*-th entry of :func:`discovery_order`.
    """
    legacy = f"seestar-{n}.local" if n > 1 else "seestar.local"
    if legacy in AVAILABLE_IPS:
        return legacy
    order = discovery_order()
    if 1 <= n <= len(order):
        return order[n - 1]
    return legacy


def resolve_ips(call_time_ips):
    """Resolve the ``ips=`` kwarg to a flat list of IP-address strings.

    Accepts the same shapes as :func:`multiple_ips`: ``None`` (current
    :data:`DEFAULT_IP`), an int (``2`` → the second scope, see
    :func:`discovery_order`), a device name (``'s50_a3497936'``), a bare
    serial number (``'a3497936'``), a hostname or IP string, the literal
    ``"all"``, or a list mixing any of these.  Unknown entries are dropped
    (with a warning printed) so the result is always a non-empty list of
    resolved IPs when input is valid.
    """
    def _resolve(ip):
        if isinstance(ip, list):
            return [_resolve(i) for i in ip]
        elif isinstance(ip, str):
            if ip in AVAILABLE_IPS:
                return AVAILABLE_IPS[ip]
            elif ip in AVAILABLE_IPS.values():
                return ip
            elif ip in DISCOVERED:
                return DISCOVERED[ip]["ip"]
            else:
                print(f"{ip} is not a valid IP address")
                return None
        elif isinstance(ip, int):
            return _resolve(_nth_scope(ip))
        elif ip is None:
            return DEFAULT_IP

    if isinstance(call_time_ips, str) and call_time_ips.lower() == "all":
        # dict.fromkeys de-duplicates while keeping insertion order: one scope
        # can hold both a discovery key and a legacy seestar-N.local key.
        call_time_ips = list(dict.fromkeys(AVAILABLE_IPS.values()))
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


# Cache of short device identifiers keyed by IP, filled by _get_device_id.
# Serial numbers don't change, so a successful lookup is reused for the
# rest of the session (failures are not cached and will be retried).
_device_ids = {}


def _get_device_id(ip, timeout=3):
    """Return a short ``model_serial`` identifier for the Seestar at *ip*.

    Queries ``get_device_state`` for the device block and condenses the
    ``product_model`` and ``sn`` fields, e.g. ``'Seestar S50'`` with serial
    ``'a3497936'`` becomes ``'s50_a3497936'``.  Uses a throwaway connection
    with a short timeout so discovery never hangs on a wedged scope.
    Returns ``None`` if the device can't be queried.
    """
    if ip in _device_ids:
        return _device_ids[ip]
    conn = _Connection(ip)
    conn._READ_TIMEOUT = timeout
    try:
        resp = conn.send({"method": "get_device_state",
                          "params": {"keys": ["device"]}}, quiet=True)
        device = resp.get("result", {}).get("device", {})
        model = (device.get("product_model") or "")
        model = model.replace("Seestar", "").replace(" ", "").lower()
        sn = device.get("sn") or ""
        dev_id = f"{model}_{sn}" if model and sn else (model or sn or None)
        if dev_id is not None:
            _device_ids[ip] = dev_id
        return dev_id
    except Exception:
        return None
    finally:
        conn.close()


def find_available_ips(n_ip=None, timeout=2, mdns=False):
    """
    Find all Seestars on the local network and fill :data:`AVAILABLE_IPS`.

    By default this delegates to :func:`discover`, which broadcasts the
    firmware's own ``scan_iscope`` probe over UDP and finds every scope on
    the subnet regardless of how many there are or what they're called.
    Pass ``mdns=True`` for the old behaviour: parallel lookups of the
    hostnames ``seestar.local``, ``seestar-2.local``, …,
    ``seestar-<n_ip>.local``, each found scope then queried for its model
    and serial number.

    Parameters
    ----------
    n_ip : int, optional
        Highest Seestar index to probe in the mDNS path.  Ignored (and
        unnecessary) during UDP discovery, which needs no upper bound.
    timeout : float, optional
        Maximum time in seconds to wait for replies.  Default is 2.
    mdns : bool, optional
        Use the legacy ``seestar-N.local`` hostname lookups instead of UDP
        broadcast discovery.  Default False.

    Examples
    --------

        >>> from seestarpy import connection as conn
        >>> conn.find_available_ips()
        ✓ Found Seestar S50 at 192.168.1.55 (s50_a3497936)
        ✓ Found Seestar S30 Pro at 192.168.1.82 (s30pro_ce545589)
        Use connection.AVAILABLE_IPS to get active addresses
        >>> conn.AVAILABLE_IPS
        {'s50_a3497936': '192.168.1.55', 's30pro_ce545589': '192.168.1.82'}

        >>> conn.find_available_ips(3, mdns=True)
        ✓ Found seestar.local at 192.168.1.243 (s50_a3497936)
        ✓ Found seestar-2.local at 192.168.1.244 (s50_b5210442)
        ✗ seestar-3.local has no active IP address
        Use connection.AVAILABLE_IPS to get active addresses

    """
    if not mdns:
        discover(timeout=timeout)
        return

    hostnames = ['seestar.local'] + [f'seestar-{i}.local' for i in
                                     range(2, (n_ip or 1) + 1)]
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
    except FuturesTimeoutError:
        pass

    # Ask each found Seestar for its model + serial number (in parallel).
    device_ids = {}
    if found:
        with ThreadPoolExecutor(max_workers=len(found)) as executor:
            id_futures = {name: executor.submit(_get_device_id, ip)
                          for name, ip in found.items()}
        device_ids = {name: fut.result() for name, fut in id_futures.items()}

    for name in hostnames:
        if name in found:
            dev_id = device_ids.get(name)
            suffix = f" ({dev_id})" if dev_id else ""
            print(f"✓ Found {name} at {found[name]}{suffix}")
        else:
            print(f"✗ {name} has no active IP address")

    print("Use connection.AVAILABLE_IPS to get active addresses")
    AVAILABLE_IPS.update(found)


def set_default_ip(n):
    """
    Point :data:`DEFAULT_IP` at one of the known Seestars.

    This is a convenience shorthand so you can switch between Seestars
    without typing IP addresses that change every time DHCP feels like it.

    Scope numbers map onto :func:`discovery_order` — serial-number order,
    which is stable from run to run and from network to network, unlike
    anything derived from IPs.  A registered ``seestar-N.local`` hostname
    still takes precedence, so scripts written against the old mDNS path
    keep their numbering:

    - ``1`` → ``seestar.local``
    - ``2`` → ``seestar-2.local``
    - ``3`` → ``seestar-3.local``
    - etc.

    Parameters
    ----------
    n : int or str
        Either a 1-based scope number, or any name :func:`resolve_ips`
        understands — a serial number (``'a3497936'``), a device name
        (``'s50_a3497936'``), a ``seestar-N.local`` hostname, or an IP.

    Raises
    ------
    KeyError
        If nothing matches.  Call :func:`discover` first to populate
        :data:`AVAILABLE_IPS`.

    Examples
    --------
    ::

        >>> from seestarpy import connection as conn
        >>> conn.discover()
        >>> conn.set_default_ip(2)
        DEFAULT_IP → 192.168.1.83 (s50_97783b61)
        >>> conn.set_default_ip('ce545589')
        DEFAULT_IP → 192.168.1.82 (s30pro_ce545589)

    """
    global DEFAULT_IP
    key = _nth_scope(n) if isinstance(n, int) else n
    if key in AVAILABLE_IPS:
        DEFAULT_IP = AVAILABLE_IPS[key]
    elif key in DISCOVERED:
        DEFAULT_IP = DISCOVERED[key]["ip"]
    elif key in AVAILABLE_IPS.values():
        DEFAULT_IP = key
    else:
        raise KeyError(
            f"{key} not found in AVAILABLE_IPS. "
            f"Call discover() first. "
            f"Available: {list(AVAILABLE_IPS.keys())}"
        )
    dev_id = _get_device_id(DEFAULT_IP)
    suffix = f" ({dev_id})" if dev_id else ""
    print(f"DEFAULT_IP \u2192 {DEFAULT_IP}{suffix}")


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
    def _send_once(self, cmd, cmd_id, quiet=False):
        message = json.dumps(cmd) + "\r\n"
        if VERBOSE_LEVEL >= 1 and not quiet:
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

    def send(self, params, quiet=False):
        cmd_id = 1
        cmd = {"id": cmd_id, "verify": True}
        cmd.update(params)

        verbose = 0 if quiet else VERBOSE_LEVEL
        with self._lock:
            last_exc = None
            for attempt in (1, 2):
                try:
                    if self._sock is None:
                        self._connect()
                    parsed = self._send_once(cmd, cmd_id, quiet=quiet)
                    if not PERSIST_CONNECTIONS:
                        self._close_locked()
                    if verbose >= 1:
                        print(f"\nRecieved: {json.dumps(parsed)}")
                    if verbose >= 2:
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
                    if verbose >= 1 and attempt == 1:
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


# Module-level auto-discovery: one UDP broadcast sweep at import, which
# registers *every* scope on the subnet in AVAILABLE_IPS (not just the first)
# and points DEFAULT_IP at the lowest-numbered one.  This runs at the END of
# the module (not at the top) because the mDNS fallback inside find_seestar()
# queries the device id via _get_device_id(), which needs _Connection.
seestar_ip = find_seestar()
DEFAULT_IP = seestar_ip if seestar_ip else "10.0.0.1"
if not AVAILABLE_IPS:
    AVAILABLE_IPS['seestar.local'] = DEFAULT_IP
