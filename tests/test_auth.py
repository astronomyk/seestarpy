"""Unit tests for auth.py — firmware 7.18+ authentication."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from seestarpy import auth


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_key_path():
    """Reset KEY_PATH before each test."""
    original = auth.KEY_PATH
    auth.KEY_PATH = None
    yield
    auth.KEY_PATH = original


@pytest.fixture
def tmp_key(tmp_path):
    """Generate a temporary RSA private key for testing."""
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=1024,  # small key, fast for tests
        )
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    except ImportError:
        pytest.skip("cryptography library not installed")

    key_file = tmp_path / "test_key.pem"
    key_file.write_bytes(pem)
    return str(key_file)


def _make_mock_socket(responses):
    """Create a mock socket that returns *responses* in order.

    Each response is a dict that will be JSON-encoded with \\r\\n.
    """
    sock = MagicMock()
    response_iter = iter(responses)

    def fake_recv(bufsize):
        try:
            resp = next(response_iter)
        except StopIteration:
            return b""
        return (json.dumps(resp) + "\r\n").encode()

    sock.recv = fake_recv
    return sock


# ---------------------------------------------------------------------------
# Key discovery
# ---------------------------------------------------------------------------

class TestKeyDiscovery:
    def test_env_var(self, tmp_key):
        with patch.dict("os.environ", {"SEESTAR_KEY_PATH": tmp_key}):
            assert auth._discover_key_path() == tmp_key

    def test_cwd(self, tmp_path, monkeypatch, tmp_key):
        import shutil
        dest = tmp_path / "seestar.pem"
        shutil.copy(tmp_key, dest)
        monkeypatch.chdir(tmp_path)
        assert auth._discover_key_path() == str(dest)

    def test_home_dir(self, tmp_path, monkeypatch, tmp_key):
        import shutil
        seestarpy_dir = tmp_path / ".seestarpy"
        seestarpy_dir.mkdir()
        dest = seestarpy_dir / "seestar.pem"
        shutil.copy(tmp_key, dest)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert auth._discover_key_path() == str(dest)

    def test_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SEESTAR_KEY_PATH", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert auth._discover_key_path() is None


class TestSetKeyPath:
    def test_set_valid_path(self, tmp_key):
        auth.set_key_path(tmp_key)
        assert auth.KEY_PATH == tmp_key

    def test_set_invalid_path(self):
        with pytest.raises(FileNotFoundError):
            auth.set_key_path("/nonexistent/key.pem")


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

class TestSignChallenge:
    def test_sign_produces_base64(self, tmp_key):
        import base64
        sig = auth.sign_challenge(tmp_key, "test_challenge_string")
        # Should be valid base64
        decoded = base64.b64decode(sig)
        assert len(decoded) > 0

    def test_sign_deterministic(self, tmp_key):
        # RSA PKCS1v15 with SHA1 is deterministic for the same key+message
        sig1 = auth.sign_challenge(tmp_key, "hello")
        sig2 = auth.sign_challenge(tmp_key, "hello")
        assert sig1 == sig2

    def test_different_challenges_different_sigs(self, tmp_key):
        sig1 = auth.sign_challenge(tmp_key, "challenge_a")
        sig2 = auth.sign_challenge(tmp_key, "challenge_b")
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# Authentication handshake
# ---------------------------------------------------------------------------

class TestAuthenticate:
    def test_skips_when_no_key(self):
        sock = MagicMock()
        assert auth.authenticate(sock) is True
        sock.sendall.assert_not_called()

    def test_old_firmware_code_103(self, tmp_key):
        """Old firmware returns error 103 for get_verify_str."""
        sock = _make_mock_socket([
            {"id": 1001, "code": 103, "error": "method not found"},
        ])
        assert auth.authenticate(sock, key_path=tmp_key) is True

    def test_old_firmware_no_challenge(self, tmp_key):
        """Firmware returns success but no challenge string."""
        sock = _make_mock_socket([
            {"id": 1001, "code": 0, "result": {}},
        ])
        assert auth.authenticate(sock, key_path=tmp_key) is True

    def test_successful_handshake(self, tmp_key):
        sock = _make_mock_socket([
            # get_verify_str response
            {"id": 1001, "code": 0, "result": {"str": "random_challenge_123"}},
            # verify_client response
            {"id": 1002, "code": 0, "result": 0},
            # pi_is_verified response
            {"id": 1003, "code": 0, "result": True},
        ])
        assert auth.authenticate(sock, key_path=tmp_key) is True

    def test_verify_rejected(self, tmp_key):
        sock = _make_mock_socket([
            {"id": 1001, "code": 0, "result": {"str": "challenge_xyz"}},
            {"id": 1002, "code": -1, "error": "signature invalid"},
        ])
        with pytest.raises(auth.AuthenticationError, match="rejected"):
            auth.authenticate(sock, key_path=tmp_key)

    def test_pi_is_verified_warning_non_fatal(self, tmp_key, capsys):
        """Non-zero pi_is_verified code is a warning, not an error."""
        sock = _make_mock_socket([
            {"id": 1001, "code": 0, "result": {"str": "challenge_abc"}},
            {"id": 1002, "code": 0, "result": 0},
            {"id": 1003, "code": -1, "result": False},
        ])
        assert auth.authenticate(sock, key_path=tmp_key) is True
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
