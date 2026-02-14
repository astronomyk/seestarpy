import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError

VERBOSE_LEVEL = 1
DEFAULT_PORT = 4700


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


def send_command(params):
    """
    Send a JSON-RPC command to the Seestar over TCP.

    Opens a short-lived TCP socket to :data:`DEFAULT_IP` on port
    :data:`DEFAULT_PORT`, sends the JSON payload, and waits for a
    ``\\r\\n``-terminated response.

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
    dict or str
        On success, a parsed JSON-RPC response dictionary with keys
        ``'jsonrpc'``, ``'Timestamp'``, ``'method'``, ``'result'``,
        ``'code'``, and ``'id'``.  If the response cannot be parsed as
        JSON, the raw response string is returned instead.

    Examples
    --------

        >>> from seestarpy.connection import send_command
        >>> send_command({"method": "test_connection"})
        {'jsonrpc': '2.0', 'Timestamp': '...', 'method': 'test_connection',
         'result': 'ok', 'code': 0, 'id': 1}

    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((DEFAULT_IP, DEFAULT_PORT))

    # params = {"method":"scope_park","params":{"equ_mode":self.is_EQ_mode}}
    cmd = {"id": 1, "verify": True}
    cmd.update(params)

    message = json.dumps(cmd) + "\r\n"
    if VERBOSE_LEVEL >= 1: print(f"\nSending: {message.strip()}")
    s.sendall(message.encode())

    # Read until we get a complete message (ends with \r\n)
    response = ""
    while "\r\n" not in response:
        chunk = s.recv(4096).decode("utf-8")
        if not chunk:
            break
        response += chunk

    if VERBOSE_LEVEL >= 1: print(f"\nRecieved: {response}")
    s.close()

    try:
        parsed = json.loads(response.split("\r\n")[0])
        method = parsed.get("method")
        result = parsed.get("result")
        code = parsed.get("code")
        error = parsed.get("error")

        if VERBOSE_LEVEL >= 2:
            print("\n✅ Response:")
            print(f"  method: {method}")
            print(f"  result: {json.dumps(result, indent=2)}")
            print(f"  code  : {code}")
            print(f"  error : {error}")
        return parsed

    except json.JSONDecodeError:
        print("⚠️ Could not parse response as JSON.")
        print("Raw response:\n", response)

        return response
