"""Phase 0 — Connection tests.

Verify basic TCP connectivity and JSON-RPC response structure.
"""

import re

import pytest

from seestarpy import raw
from seestarpy import connection as conn

pytestmark = pytest.mark.integration


def test_find_seestar_returns_ip(seestar_ip):
    """DEFAULT_IP should be a valid IPv4 address string."""
    assert re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", seestar_ip)


def test_send_command_returns_dict(verified_connection):
    """test_connection() should return a dict with code 0."""
    result = verified_connection
    assert isinstance(result, dict)
    assert result["code"] == 0


def test_send_command_response_structure(verified_connection):
    """Response must contain the standard JSON-RPC keys."""
    result = verified_connection
    for key in ("jsonrpc", "Timestamp", "method", "code", "id"):
        assert key in result, f"Missing key: {key}"


def test_send_command_invalid_method():
    """Sending a bogus method should return an error response."""
    result = raw.random_command("bogus_method_that_does_not_exist")
    assert isinstance(result, dict)
    assert result.get("code") != 0 or "error" in result
