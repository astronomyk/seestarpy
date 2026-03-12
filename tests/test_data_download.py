"""Unit tests for data.download_file(), delete_files(), and _build_http_url()."""

import os
from unittest.mock import MagicMock, call, patch

import pytest
from smb.smb_structs import OperationFailure

from seestarpy.data import _build_http_url, delete_files, download_file


class TestBuildHttpUrl:
    @patch("seestarpy.data.connection")
    def test_simple_path(self, mock_conn):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        url = _build_http_url("MyWorks/Lunar/thumb.jpg")
        assert url == "http://192.168.1.246/MyWorks/Lunar/thumb.jpg"

    @patch("seestarpy.data.connection")
    def test_spaces_encoded(self, mock_conn):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        url = _build_http_url("MyWorks/M 81/DSO_Stacked_3_M 81_20.0s_20260227_225203.fit")
        assert url == (
            "http://192.168.1.246/MyWorks/M%2081/"
            "DSO_Stacked_3_M%2081_20.0s_20260227_225203.fit"
        )

    @patch("seestarpy.data.connection")
    def test_slashes_preserved(self, mock_conn):
        mock_conn.DEFAULT_IP = "10.0.0.1"
        url = _build_http_url("MyWorks/a/b/c.fit")
        assert "MyWorks/a/b/c.fit" in url


class TestDownloadFile:
    @patch("seestarpy.data.connection")
    @patch("seestarpy.data.urllib.request.urlopen")
    def test_downloads_file(self, mock_urlopen, mock_conn, tmp_path):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        content = b"SIMPLE  = T" + b"\x00" * 1000
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [content, b""]
        mock_urlopen.return_value = mock_resp

        result = download_file("Lunar", "thumb.jpg", dest=str(tmp_path))

        assert os.path.isabs(result)
        assert result.endswith("thumb.jpg")
        assert os.path.exists(result)
        with open(result, "rb") as f:
            assert f.read() == content

    @patch("seestarpy.data.connection")
    @patch("seestarpy.data.urllib.request.urlopen")
    def test_url_has_correct_path(self, mock_urlopen, mock_conn, tmp_path):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [b"data", b""]
        mock_urlopen.return_value = mock_resp

        download_file("M 81", "stack.fit", dest=str(tmp_path))

        called_url = mock_urlopen.call_args[0][0]
        assert "M%2081" in called_url
        assert called_url.startswith("http://192.168.1.246/MyWorks/")

    @patch("seestarpy.data.connection")
    @patch("seestarpy.data.urllib.request.urlopen")
    def test_404_raises_file_not_found(self, mock_urlopen, mock_conn, tmp_path):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://...", code=404, msg="Not Found", hdrs={}, fp=None
        )

        with pytest.raises(FileNotFoundError, match="File not found"):
            download_file("M 81", "missing.fit", dest=str(tmp_path))

    @patch("seestarpy.data.connection")
    @patch("seestarpy.data.urllib.request.urlopen")
    def test_500_raises_connection_error(self, mock_urlopen, mock_conn, tmp_path):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://...", code=500, msg="Internal Server Error", hdrs={}, fp=None
        )

        with pytest.raises(ConnectionError, match="HTTP 500"):
            download_file("M 81", "bad.fit", dest=str(tmp_path))

    @patch("seestarpy.data.connection")
    @patch("seestarpy.data.urllib.request.urlopen")
    def test_unreachable_raises_connection_error(self, mock_urlopen, mock_conn, tmp_path):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("timed out")

        with pytest.raises(ConnectionError, match="Cannot reach Seestar"):
            download_file("M 81", "file.fit", dest=str(tmp_path))

    @patch("seestarpy.data.connection")
    @patch("seestarpy.data.urllib.request.urlopen")
    def test_creates_dest_directory(self, mock_urlopen, mock_conn, tmp_path):
        mock_conn.DEFAULT_IP = "192.168.1.246"
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [b"x", b""]
        mock_urlopen.return_value = mock_resp

        nested = str(tmp_path / "a" / "b" / "c")
        result = download_file("Lunar", "f.fit", dest=nested)
        assert os.path.exists(result)


class TestDeleteFiles:
    @patch("seestarpy.data._connect_smb")
    def test_deletes_files(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = delete_files("M 81", ["a.fit", "b.jpg"])

        assert result == {"a.fit": True, "b.jpg": True}
        mock_conn.deleteFiles.assert_has_calls([
            call("EMMC Images", "MyWorks/M 81/a.fit"),
            call("EMMC Images", "MyWorks/M 81/b.jpg"),
        ])
        mock_conn.close.assert_called_once()

    @patch("seestarpy.data._connect_smb")
    def test_missing_file_returns_false(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.deleteFiles.side_effect = [
            None,
            OperationFailure("not found", []),
        ]

        result = delete_files("M 81", ["exists.fit", "missing.fit"])

        assert result == {"exists.fit": True, "missing.fit": False}
        mock_conn.close.assert_called_once()

    @patch("seestarpy.data._connect_smb")
    def test_empty_list(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = delete_files("M 81", [])

        assert result == {}
        mock_conn.deleteFiles.assert_not_called()
        mock_conn.close.assert_called_once()
