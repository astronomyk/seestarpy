"""Unit tests for the connection/session layer in connection.py.

Covers the thread-local target-IP resolution (no shared-global race),
nested @multiple_ips scope inheritance, and the persistent _Connection
(reuse one authenticated socket; reconnect + retry once on drop).
"""

import json
from unittest.mock import patch

import pytest

from seestarpy import connection


@pytest.fixture(autouse=True)
def _isolate_connection_state():
    """Quiet logging, no auth, fresh pool + thread-local for each test."""
    orig_ip = connection.DEFAULT_IP
    orig_avail = dict(connection.AVAILABLE_IPS)
    orig_verbose = connection.VERBOSE_LEVEL
    connection.VERBOSE_LEVEL = 0
    connection.close_connections()
    if hasattr(connection._active, "ip"):
        del connection._active.ip
    with patch("seestarpy.auth.KEY_PATH", None):
        yield
    connection.close_connections()
    connection.DEFAULT_IP = orig_ip
    connection.AVAILABLE_IPS = orig_avail
    connection.VERBOSE_LEVEL = orig_verbose


# --------------------------------------------------------------------------
# current_ip / multiple_ips
# --------------------------------------------------------------------------

class TestCurrentIp:
    def test_defaults_to_default_ip(self):
        connection.DEFAULT_IP = "9.9.9.9"
        assert connection.current_ip() == "9.9.9.9"


class TestMultipleIps:
    def test_does_not_mutate_global(self):
        """The race fix: broadcasting must not clobber DEFAULT_IP."""
        connection.DEFAULT_IP = "1.1.1.1"
        connection.AVAILABLE_IPS = {"a": "1.1.1.1", "b": "2.2.2.2"}

        @connection.multiple_ips
        def who():
            return connection.current_ip()

        result = who(ips=["1.1.1.1", "2.2.2.2"])
        # Each worker sees its own IP — no cross-talk.
        assert result == {"1.1.1.1": "1.1.1.1", "2.2.2.2": "2.2.2.2"}
        # And the module global is untouched afterwards.
        assert connection.DEFAULT_IP == "1.1.1.1"

    def test_single_ip_returns_scalar(self):
        connection.DEFAULT_IP = "1.1.1.1"

        @connection.multiple_ips
        def who():
            return connection.current_ip()

        assert who() == "1.1.1.1"

    def test_nested_call_inherits_scope(self):
        """A nested decorated call with no ips= inherits the outer IP."""
        connection.DEFAULT_IP = "1.1.1.1"
        connection.AVAILABLE_IPS = {"a": "1.1.1.1", "b": "2.2.2.2"}

        @connection.multiple_ips
        def inner():
            return connection.current_ip()

        @connection.multiple_ips
        def outer():
            return inner()  # no ips= → should inherit outer's scope

        assert outer(ips="2.2.2.2") == "2.2.2.2"

    def test_thread_local_cleared_after_call(self):
        connection.DEFAULT_IP = "1.1.1.1"

        @connection.multiple_ips
        def noop():
            return None

        noop()
        # Back on the main thread the override must be gone.
        assert connection.current_ip() == "1.1.1.1"


# --------------------------------------------------------------------------
# Persistent _Connection
# --------------------------------------------------------------------------

class _FakeSock:
    """Scripted socket: each sendall queues the next reply for recv.

    ``drop_on`` is a set of 1-based send indices on which recv should report
    a closed connection (empty bytes) to exercise the reconnect path.
    """

    def __init__(self, replies, drop_on=()):
        self._replies = list(replies)
        self._recv = b""
        self._sends = 0
        self.drop_on = set(drop_on)
        self.closed = False
        self.connected_to = None

    def settimeout(self, t):
        pass

    def connect(self, addr):
        self.connected_to = addr

    def sendall(self, data):
        self._sends += 1
        if self._sends in self.drop_on:
            self._recv = b""  # simulate a dropped/half-open socket
            return
        reply = self._replies.pop(0) if self._replies else {"id": 1, "code": 0}
        self._recv += (json.dumps(reply) + "\r\n").encode()

    def recv(self, n):
        if not self._recv:
            return b""  # peer closed
        chunk, self._recv = self._recv[:n], self._recv[n:]
        return chunk

    def close(self):
        self.closed = True


class TestPersistentConnection:
    def test_reuses_one_socket_across_calls(self):
        connection.DEFAULT_IP = "9.9.9.9"
        sock = _FakeSock([
            {"id": 1, "method": "a", "result": "ok", "code": 0},
            {"id": 1, "method": "b", "result": "ok", "code": 0},
        ])
        created = []

        def factory(*a, **k):
            created.append(sock)
            return sock

        with patch("seestarpy.connection.socket.socket", side_effect=factory):
            r1 = connection.send_command({"method": "a"})
            r2 = connection.send_command({"method": "b"})

        assert r1["method"] == "a" and r2["method"] == "b"
        assert len(created) == 1            # only one socket opened
        assert sock.connected_to == ("9.9.9.9", connection.DEFAULT_PORT)

    def test_reconnects_after_drop(self):
        connection.DEFAULT_IP = "9.9.9.9"
        dropped = _FakeSock([], drop_on=(1,))          # closes on first send
        fresh = _FakeSock([{"id": 1, "result": "ok", "code": 0}])
        created = []

        def factory(*a, **k):
            sock = dropped if not created else fresh
            created.append(sock)
            return sock

        with patch("seestarpy.connection.socket.socket", side_effect=factory):
            r = connection.send_command({"method": "test_connection"})

        assert r["result"] == "ok"
        assert len(created) == 2            # reconnected once
        assert dropped.closed is True

    def test_raises_after_two_failures(self):
        connection.DEFAULT_IP = "9.9.9.9"

        def factory(*a, **k):
            return _FakeSock([], drop_on=(1,))         # always drops

        with patch("seestarpy.connection.socket.socket", side_effect=factory):
            with pytest.raises(ConnectionError, match="failed after reconnect"):
                connection.send_command({"method": "x"})

    def test_non_persistent_closes_each_call(self):
        connection.DEFAULT_IP = "9.9.9.9"
        socks = [
            _FakeSock([{"id": 1, "result": "ok", "code": 0}]),
            _FakeSock([{"id": 1, "result": "ok", "code": 0}]),
        ]
        created = []

        def factory(*a, **k):
            sock = socks[len(created)]
            created.append(sock)
            return sock

        with patch("seestarpy.connection.PERSIST_CONNECTIONS", False), \
             patch("seestarpy.connection.socket.socket", side_effect=factory):
            connection.send_command({"method": "a"})
            connection.send_command({"method": "b"})

        assert len(created) == 2            # a fresh socket per call
        assert socks[0].closed is True
