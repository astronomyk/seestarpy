"""Test gating: offline by default, live hardware strictly opt-in.

A plain ``pytest`` run must never touch a telescope.  The suite therefore
has three tiers, selected by command-line flags rather than by whether a
scope happens to answer:

======================  ====================================================
``pytest``              Offline only.  Every test marked ``integration``
                        is skipped, so nothing reaches the network.
``pytest --live``       Adds the live-hardware tests, including ones that
                        slew, park and open the arm.
``pytest --live         Live tests that do **not** move the telescope, for
--no-movement``         a scope that is still in its box or otherwise has
                        no freedom of movement.
======================  ====================================================

Deciding by flag and not by reachability is deliberate: the old
behaviour ran the whole live suite automatically whenever a Seestar
answered on port 4700, which meant an innocent ``pytest`` on the
observing laptop started driving the mount.
"""

import pathlib
import socket

import pytest

_INTEGRATION_DIR = pathlib.Path(__file__).parent / "integration"


def pytest_addoption(parser):
    group = parser.getgroup("seestar")
    group.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run the live-hardware tests against a real Seestar. "
             "Without this, every test marked 'integration' is skipped.",
    )
    group.addoption(
        "--no-movement",
        action="store_true",
        default=False,
        help="With --live, skip tests that move the telescope (slew, park, "
             "open the arm, focus). Use when the scope cannot move freely.",
    )


def _seestar_reachable(port=4700, timeout=5):
    """Return True if a TCP connection to the Seestar succeeds.

    Only ever called when ``--live`` was passed, so the default run pays
    no network timeout.
    """
    try:
        from seestarpy.connection import DEFAULT_IP
        ip = DEFAULT_IP
    except Exception:
        try:
            ip = socket.gethostbyname("seestar.local")
        except socket.gaierror:
            ip = "10.0.0.1"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _is_live(item):
    """A test needs hardware if it is marked, or lives in integration/."""
    if item.get_closest_marker("integration") is not None:
        return True
    return _INTEGRATION_DIR in pathlib.Path(item.fspath).parents


def pytest_collection_modifyitems(config, items):
    live = config.getoption("--live")
    no_movement = config.getoption("--no-movement")

    if not live:
        skip = pytest.mark.skip(
            reason="live-hardware test; pass --live to run it")
        for item in items:
            if _is_live(item):
                item.add_marker(skip)
        return

    # --live given: the scope must actually be there, or every one of these
    # fails with a connection error rather than an explanatory skip.
    if not _seestar_reachable():
        skip = pytest.mark.skip(reason="No Seestar reachable on the network")
        for item in items:
            if _is_live(item):
                item.add_marker(skip)
        return

    if no_movement:
        skip = pytest.mark.skip(
            reason="moves the telescope; --no-movement was given")
        for item in items:
            if item.get_closest_marker("movement") is not None:
                item.add_marker(skip)
