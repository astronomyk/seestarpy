import socket
import pathlib

import pytest


def _seestar_reachable(host="seestar.local", port=4700, timeout=3):
    """Return True if a TCP connection to the Seestar succeeds."""
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        # mDNS name not resolvable — try direct IP fallback
        ip = "10.0.0.1"

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


_INTEGRATION_DIR = pathlib.Path(__file__).parent / "integration"


def pytest_collection_modifyitems(config, items):
    """Skip all tests under tests/integration/ when no Seestar is reachable."""
    # Only probe the network once per collection run
    need_check = any(
        _INTEGRATION_DIR in pathlib.Path(item.fspath).parents
        for item in items
    )
    if not need_check:
        return

    reachable = _seestar_reachable()
    if reachable:
        return

    skip_marker = pytest.mark.skip(reason="No Seestar reachable on the network")
    for item in items:
        if _INTEGRATION_DIR in pathlib.Path(item.fspath).parents:
            item.add_marker(skip_marker)
