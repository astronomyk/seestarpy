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


@pytest.fixture(scope="module")
def seestar_with_data(verified_connection):
    """Find a Seestar that has observation folders and set it as DEFAULT_IP.

    Tries the default Seestar first.  If it has no folders, discovers all
    available Seestars and queries each one sequentially (avoids event
    collisions that can occur with parallel ``ips='all'`` queries).
    Restores DEFAULT_IP on teardown.
    """
    original_ip = conn.DEFAULT_IP

    result = data.list_folders()
    if result:
        yield result
        return

    # Default has no data — try each seestar individually
    conn.find_available_ips(3)
    for ip in conn.AVAILABLE_IPS.values():
        if ip == original_ip:
            continue
        folders = data.list_folders(ips=ip)
        if folders:
            conn.DEFAULT_IP = ip
            yield folders
            conn.DEFAULT_IP = original_ip
            return

    pytest.skip("No folders found on any Seestar")


@pytest.fixture(scope="module")
def folders(seestar_with_data):
    """Return the folder listing from a Seestar that has data."""
    return seestar_with_data


@pytest.fixture(scope="module")
def first_folder(folders):
    """Return the name of the first folder."""
    return next(iter(folders))


# ── list_folders ──────────────────────────────────────────────────────

def test_list_folders(verified_connection):
    """list_folders should return a dict mapping folder names to file counts."""
    result = data.list_folders()
    assert isinstance(result, dict)
    for name, count in result.items():
        assert isinstance(name, str)
        assert isinstance(count, int)


def test_list_folders_multi_ip(verified_connection):
    """list_folders(ips='all') should return a dict keyed by IP."""
    conn.find_available_ips(3)
    if len(conn.AVAILABLE_IPS) < 2:
        pytest.skip("Only one Seestar on the network")

    result = data.list_folders(ips="all")
    assert isinstance(result, dict)
    assert len(result) == len(conn.AVAILABLE_IPS)
    for ip, folders in result.items():
        assert isinstance(folders, dict)


# ── list_folder_contents ─────────────────────────────────────────────

def test_list_folder_contents(verified_connection, first_folder):
    """Pick the first folder and verify contents is a dict of {str: int}."""
    contents = data.list_folder_contents(first_folder)
    assert isinstance(contents, dict)
    for fname, size in contents.items():
        assert isinstance(fname, str)
        assert isinstance(size, int)


def test_list_folder_contents_missing_folder(verified_connection):
    """Querying a nonexistent folder should return an empty dict."""
    result = data.list_folder_contents("__nonexistent_folder__")
    assert result == {}


def test_list_folder_contents_filetype_star(verified_connection, first_folder):
    """filetype='*' should return all files (same as default)."""
    all_files = data.list_folder_contents(first_folder)
    star_files = data.list_folder_contents(first_folder, filetype="*")
    assert star_files == all_files


def test_list_folder_contents_filetype_fit(verified_connection, first_folder):
    """filetype='fit' should return only .fit files."""
    contents = data.list_folder_contents(first_folder, filetype="fit")
    for fname in contents:
        assert fname.endswith(".fit"), f"Expected .fit file, got {fname}"


def test_list_folder_contents_filetype_jpg(verified_connection, first_folder):
    """filetype='jpg' should return full-size JPEGs only (no thumbnails)."""
    contents = data.list_folder_contents(first_folder, filetype="jpg")
    for fname in contents:
        assert fname.endswith(".jpg"), f"Expected .jpg file, got {fname}"
        assert not fname.endswith("_thn.jpg"), f"Thumbnail leaked through: {fname}"


def test_list_folder_contents_filetype_thn(verified_connection, first_folder):
    """filetype='thn.jpg' should return only thumbnail JPEGs."""
    contents = data.list_folder_contents(first_folder, filetype="thn.jpg")
    for fname in contents:
        assert fname.endswith("_thn.jpg"), f"Expected _thn.jpg file, got {fname}"


def test_list_folder_contents_filetype_all_jpg(verified_connection, first_folder):
    """filetype='*jpg' should return all JPEGs (full-size + thumbnails)."""
    contents = data.list_folder_contents(first_folder, filetype="*jpg")
    for fname in contents:
        assert fname.endswith(".jpg"), f"Expected .jpg file, got {fname}"

    # Should be the union of 'jpg' and 'thn.jpg'
    jpg_only = data.list_folder_contents(first_folder, filetype="jpg")
    thn_only = data.list_folder_contents(first_folder, filetype="thn.jpg")
    assert set(contents) == set(jpg_only) | set(thn_only)


def test_list_folder_contents_filetype_invalid(verified_connection):
    """An invalid filetype should raise ValueError."""
    with pytest.raises(ValueError, match="filetype must be one of"):
        data.list_folder_contents("anything", filetype="png")


def test_list_folder_contents_filters_are_subset(verified_connection, first_folder):
    """Each filter should return a subset of the unfiltered listing."""
    all_files = data.list_folder_contents(first_folder)
    for ft in ("fit", "jpg", "thn.jpg", "*jpg"):
        filtered = data.list_folder_contents(first_folder, filetype=ft)
        assert set(filtered).issubset(set(all_files)), (
            f"filetype={ft!r} returned files not in unfiltered listing"
        )


# ── download_folder ──────────────────────────────────────────────────

def test_download_folder(verified_connection, tmp_path, folders):
    """Download the smallest folder and verify file count matches SMB listing."""
    smallest = min(folders, key=folders.get)
    # Use list_folder_contents (SMB) for the true file count, since
    # list_folders (get_albums) reports album entries, not individual files.
    expected_count = len(data.list_folder_contents(smallest))

    data.download_folder(folder=smallest, dest=str(tmp_path))

    downloaded = list((tmp_path / smallest).iterdir())
    assert len(downloaded) == expected_count
