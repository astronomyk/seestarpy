"""Unit tests for CrowdSky server API client (crowdsky/server.py)."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from seestarpy.crowdsky import server


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module globals before each test."""
    server.USERNAME = ""
    server.PASSWORD = ""
    server.BASE_URL = "https://crowdsky.univie.ac.at"
    yield


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

class TestCredentials:
    def test_set_credentials(self):
        server.set_credentials("alice", "s3cret")
        assert server.USERNAME == "alice"
        assert server.PASSWORD == "s3cret"

    def test_get_auth_raises_when_empty(self):
        with pytest.raises(RuntimeError, match="credentials not set"):
            server._get_auth()

    def test_get_auth_raises_when_partial(self):
        server.USERNAME = "alice"
        with pytest.raises(RuntimeError, match="credentials not set"):
            server._get_auth()

    def test_get_auth_returns_tuple(self):
        server.set_credentials("alice", "s3cret")
        assert server._get_auth() == ("alice", "s3cret")

    def test_set_base_url(self):
        server.set_base_url("https://staging.example.com/")
        assert server.BASE_URL == "https://staging.example.com"

    def test_set_base_url_no_trailing_slash(self):
        server.set_base_url("https://example.com")
        assert server.BASE_URL == "https://example.com"


# ---------------------------------------------------------------------------
# _request helper
# ---------------------------------------------------------------------------

class TestRequestHelper:
    def setup_method(self):
        server.set_credentials("alice", "s3cret")

    @patch("seestarpy.crowdsky.server.requests.request")
    def test_401_raises_auth_error(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_req.return_value = mock_resp

        with pytest.raises(RuntimeError, match="authentication failed"):
            server._request("GET", "/api/my_stacks.php")

    @patch("seestarpy.crowdsky.server.requests.request")
    def test_other_http_errors_propagate(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("Server Error")
        mock_req.return_value = mock_resp

        with pytest.raises(Exception, match="Server Error"):
            server._request("GET", "/api/my_stacks.php")

    @patch("seestarpy.crowdsky.server.requests.request")
    def test_injects_auth_and_timeout(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_req.return_value = mock_resp

        server._request("GET", "/api/my_stacks.php")

        mock_req.assert_called_once_with(
            "GET",
            "https://crowdsky.univie.ac.at/api/my_stacks.php",
            timeout=(30, 300),
            auth=("alice", "s3cret"),
        )


# ---------------------------------------------------------------------------
# list_stacks
# ---------------------------------------------------------------------------

class TestListStacks:
    def setup_method(self):
        server.set_credentials("alice", "s3cret")

    @patch("seestarpy.crowdsky.server._request")
    def test_returns_parsed_json(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"chunk_key": "abc123", "object_name": "M 81"},
        ]
        mock_req.return_value = mock_resp

        result = server.list_stacks()

        assert len(result) == 1
        assert result[0]["chunk_key"] == "abc123"
        mock_req.assert_called_once_with(
            "GET", "/api/my_stacks.php", params={},
        )

    @patch("seestarpy.crowdsky.server._request")
    def test_passes_object_filter(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_req.return_value = mock_resp

        server.list_stacks(object_name="M 42")

        mock_req.assert_called_once_with(
            "GET", "/api/my_stacks.php", params={"object": "M 42"},
        )


# ---------------------------------------------------------------------------
# upload_stack
# ---------------------------------------------------------------------------

class TestUploadStack:
    def setup_method(self):
        server.set_credentials("alice", "s3cret")

    @patch("seestarpy.crowdsky.server._request")
    def test_success(self, mock_req, tmp_path):
        fits_file = tmp_path / "test.fit"
        fits_file.write_bytes(b"FITS DATA")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "stack_id": 42,
            "chunk_key": "abc123",
            "telescope_id": 7,
        }
        mock_req.return_value = mock_resp

        result = server.upload_stack(str(fits_file))

        assert result["ok"] is True
        assert result["stack_id"] == 42
        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args
        assert call_kwargs[0] == ("POST", "/api/upload_stack.php")

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError, match="FITS file not found"):
            server.upload_stack("/nonexistent/path.fit")


# ---------------------------------------------------------------------------
# download_stack
# ---------------------------------------------------------------------------

class TestDownloadStack:
    def setup_method(self):
        server.set_credentials("alice", "s3cret")

    @patch("seestarpy.crowdsky.server._request")
    def test_single_key_downloads_file(self, mock_req, tmp_path):
        mock_resp = MagicMock()
        mock_resp.headers = {
            "Content-Disposition": 'attachment; filename="M81_chunk.fits"',
        }
        mock_resp.iter_content.return_value = [b"FITS", b"DATA"]
        mock_req.return_value = mock_resp

        result = server.download_stack("abc123", dest=str(tmp_path))

        assert len(result) == 1
        assert result[0].name == "M81_chunk.fits"
        assert (tmp_path / "M81_chunk.fits").read_bytes() == b"FITSDATA"

    @patch("seestarpy.crowdsky.server._request")
    def test_fallback_filename_from_key(self, mock_req, tmp_path):
        mock_resp = MagicMock()
        mock_resp.headers = {}
        mock_resp.iter_content.return_value = [b"DATA"]
        mock_req.return_value = mock_resp

        result = server.download_stack("xyz789", dest=str(tmp_path))

        assert result[0].name == "xyz789.fits"

    @patch("seestarpy.crowdsky.server._request")
    def test_multiple_keys(self, mock_req, tmp_path):
        mock_resp = MagicMock()
        mock_resp.headers = {}
        mock_resp.iter_content.return_value = [b"DATA"]
        mock_req.return_value = mock_resp

        result = server.download_stack(["key1", "key2"], dest=str(tmp_path))

        assert len(result) == 2
        assert mock_req.call_count == 2
