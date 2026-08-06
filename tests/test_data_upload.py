"""Unit tests for data.upload_files() and data.upload_folder()."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from smb.smb_structs import OperationFailure

from seestarpy.data import upload_files, upload_folder


def _make_local_files(tmp_path, spec):
    """Create local files from {name: bytes} and return their paths."""
    paths = {}
    for name, content in spec.items():
        p = tmp_path / name
        p.write_bytes(content)
        paths[name] = str(p)
    return paths


def _remote_entry(name, size):
    """A stand-in for a pysmb SharedFile as returned by listPath."""
    return SimpleNamespace(filename=name, file_size=size)


class TestUploadFiles:
    @patch("seestarpy.data._connect_smb")
    def test_uploads_files(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_conn.listPath.return_value = []  # nothing present yet
        mock_connect.return_value = mock_conn

        paths = _make_local_files(
            tmp_path, {"a.fit": b"x" * 10, "b.fit": b"y" * 20})

        result = upload_files("NGC 3310_sub", list(paths.values()))

        assert result == {"a.fit": True, "b.fit": True}
        # both files stored under the right remote path
        stored = {c.args[1] for c in mock_conn.storeFile.call_args_list}
        assert stored == {
            "MyWorks/NGC 3310_sub/a.fit",
            "MyWorks/NGC 3310_sub/b.fit",
        }
        mock_conn.createDirectory.assert_called_once_with(
            "EMMC Images", "MyWorks/NGC 3310_sub")
        mock_conn.close.assert_called_once()

    @patch("seestarpy.data._connect_smb")
    def test_skips_existing_same_size(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        paths = _make_local_files(
            tmp_path, {"a.fit": b"x" * 10, "b.fit": b"y" * 20})
        # a.fit already present at the same size -> skipped
        mock_conn.listPath.return_value = [_remote_entry("a.fit", 10)]

        result = upload_files("F", list(paths.values()))

        assert result == {"a.fit": True, "b.fit": True}
        mock_conn.storeFile.assert_called_once()
        assert mock_conn.storeFile.call_args.args[1] == "MyWorks/F/b.fit"

    @patch("seestarpy.data._connect_smb")
    def test_reuploads_when_size_differs(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        paths = _make_local_files(tmp_path, {"a.fit": b"x" * 10})
        # present but wrong size -> must re-upload
        mock_conn.listPath.return_value = [_remote_entry("a.fit", 999)]

        result = upload_files("F", list(paths.values()))

        assert result == {"a.fit": True}
        mock_conn.storeFile.assert_called_once()

    @patch("seestarpy.data._connect_smb")
    def test_overwrite_ignores_existing(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        paths = _make_local_files(tmp_path, {"a.fit": b"x" * 10})
        mock_conn.listPath.return_value = [_remote_entry("a.fit", 10)]

        result = upload_files("F", list(paths.values()), overwrite=True)

        assert result == {"a.fit": True}
        mock_conn.storeFile.assert_called_once()
        # listPath not consulted when overwriting
        mock_conn.listPath.assert_not_called()

    @patch("seestarpy.data._connect_smb")
    def test_store_failure_returns_false(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.listPath.return_value = []
        mock_conn.storeFile.side_effect = OperationFailure("denied", [])
        paths = _make_local_files(tmp_path, {"a.fit": b"x" * 10})

        result = upload_files("F", list(paths.values()))

        assert result == {"a.fit": False}
        mock_conn.close.assert_called_once()

    @patch("seestarpy.data._connect_smb")
    def test_existing_dir_is_tolerated(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.listPath.return_value = []
        # createDirectory raises because the folder already exists
        mock_conn.createDirectory.side_effect = OperationFailure("exists", [])
        paths = _make_local_files(tmp_path, {"a.fit": b"x" * 10})

        result = upload_files("F", list(paths.values()))

        assert result == {"a.fit": True}
        mock_conn.storeFile.assert_called_once()

    @patch("seestarpy.data._connect_smb")
    def test_empty_list_does_not_connect(self, mock_connect):
        result = upload_files("F", [])
        assert result == {}
        mock_connect.assert_not_called()


class TestUploadFolder:
    @patch("seestarpy.data._connect_smb")
    def test_pattern_filters_files(self, mock_connect, tmp_path):
        mock_conn = MagicMock()
        mock_conn.listPath.return_value = []
        mock_connect.return_value = mock_conn
        _make_local_files(
            tmp_path,
            {"a.fit": b"1", "b.fit": b"2", "note.txt": b"x", "c.jpg": b"y"})

        result = upload_folder(str(tmp_path), folder="F", pattern="*.fit")

        assert set(result) == {"a.fit", "b.fit"}
        stored = {c.args[1] for c in mock_conn.storeFile.call_args_list}
        assert stored == {"MyWorks/F/a.fit", "MyWorks/F/b.fit"}

    @patch("seestarpy.data._connect_smb")
    def test_folder_defaults_to_basename(self, mock_connect, tmp_path):
        target = tmp_path / "NGC 3310"
        target.mkdir()
        (target / "a.fit").write_bytes(b"1")
        mock_conn = MagicMock()
        mock_conn.listPath.return_value = []
        mock_connect.return_value = mock_conn

        upload_folder(str(target), pattern="*.fit")

        mock_conn.createDirectory.assert_called_once_with(
            "EMMC Images", "MyWorks/NGC 3310")
        assert mock_conn.storeFile.call_args.args[1] == "MyWorks/NGC 3310/a.fit"

    @patch("seestarpy.data._connect_smb")
    def test_subdirectories_ignored(self, mock_connect, tmp_path):
        (tmp_path / "a.fit").write_bytes(b"1")
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "deep.fit").write_bytes(b"2")
        mock_conn = MagicMock()
        mock_conn.listPath.return_value = []
        mock_connect.return_value = mock_conn

        result = upload_folder(str(tmp_path), folder="F", pattern="*")

        assert set(result) == {"a.fit"}

    @patch("seestarpy.data._connect_smb")
    def test_empty_dir_no_connect(self, mock_connect, tmp_path):
        result = upload_folder(str(tmp_path), folder="F", pattern="*.fit")
        assert result == {}
        mock_connect.assert_not_called()

    def test_missing_dir_raises(self):
        with pytest.raises(NotADirectoryError):
            upload_folder(os.path.join("does", "not", "exist"), folder="F")
