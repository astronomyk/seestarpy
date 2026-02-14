import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError

VERBOSE_LEVEL = 1
DEFAULT_PORT = 4700


def find_seestar():
    """
    Find a Seestar on the local network using mDNS hostname resolution.

    Returns
    -------
    str or None
        The IP address of the Seestar if found, otherwise ``None``.
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

    Resolves hostnames ``seestar.local``, ``seestar-2.local``, etc.
    and updates :data:`AVAILABLE_IPS` with the results.

    Parameters
    ----------
    n_ip : int
        Maximum number of Seestars to search for.
    timeout : float, optional
        Timeout in seconds for the parallel lookups. Default is 2.
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
    Send a generic JSON command to the Seestar

    Parameters
    ----------
    params : dict
        Expected format: {"method": <method-name>, "params": <params-dict>}

    Returns
    -------
    response : dict | str
        {'jsonrpc': '2.0',
        'Timestamp': float,
        'method': str,
        'result': dict,
        'code': 0,
        'id': 1}

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
