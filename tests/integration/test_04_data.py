"""Phase 4 — Data module tests.

Gated by SMB availability (port 445). Excluded: ``delete_folder`` is
destructive and irreversible.
"""

import socket

import pytest

from seestarpy import data
from seestarpy import connection as conn

pytestmark = pytest.mark.integration


def _smb_reachable(ip=None, port=445, timeout=3):
    """Return True if SMB port is open on the Seestar."""
    ip = ip or conn.DEFAULT_IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


@pytest.fixture(scope="module", autouse=True)
def require_smb():
    """Skip the entire module if SMB is not reachable."""
    if not _smb_reachable():
        pytest.skip("SMB port 445 not reachable on Seestar")


def test_list_folders(verified_connection):
    """list_folders should return a dict mapping folder names to file counts."""
    result = data.list_folders()
    assert isinstance(result, dict)
    # Values should be ints (file counts)
    for name, count in result.items():
        assert isinstance(name, str)
        assert isinstance(count, int)


def test_list_folder_contents(verified_connection):
    """Pick the first folder and verify contents is a dict of {str: int}."""
    folders = data.list_folders()
    if not folders:
        pytest.skip("No folders on Seestar to inspect")

    first_folder = next(iter(folders))
    contents = data.list_folder_contents(first_folder)
    assert isinstance(contents, dict)
    for fname, size in contents.items():
        assert isinstance(fname, str)
        assert isinstance(size, int)


def test_download_folder(verified_connection, tmp_path):
    """Download the smallest folder and verify file count matches."""
    folders = data.list_folders()
    if not folders:
        pytest.skip("No folders on Seestar to download")

    # Pick the folder with the fewest files
    smallest = min(folders, key=folders.get)
    expected_count = folders[smallest]

    data.download_folder(folder=smallest, dest=str(tmp_path))

    downloaded = list((tmp_path / smallest).iterdir())
    assert len(downloaded) == expected_count
