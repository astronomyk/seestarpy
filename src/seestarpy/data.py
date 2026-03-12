# seestar_data_utils.py
# Utilities for listing, deleting, and downloading data from a Seestar S50
# File listing uses JSON-RPC over port 4700 (paginated)
# Deleting uses pysmb over direct SMB (port 445)
# Downloading uses mounted SMB paths on Unix; Windows uses native SMB paths

import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict

from smb.SMBConnection import SMBConnection
from smb.smb_structs import OperationFailure
from . import connection
from .connection import multiple_ips
from .raw import get_albums, get_img_file_page_number, get_img_file_page_name

SHARE_NAME = "EMMC Images"
ROOT_DIR = "MyWorks"
HTTP_PORT = 80


def _connect_smb() -> SMBConnection:
    """
    Create and return an SMBConnection using direct TCP (port 445).

    Uses the module-level :data:`connection.DEFAULT_IP`, which the
    :func:`~connection.multiple_ips` decorator swaps per-thread.

    Returns
    -------
    SMBConnection
        An open SMB connection to the Seestar.

    Raises
    ------
    ConnectionError
        If the connection to the Seestar fails.
    """
    ip = connection.DEFAULT_IP
    conn = SMBConnection(
        username='',
        password='',
        my_name='raspi',
        remote_name='seestar',
        use_ntlm_v2=False,
        is_direct_tcp=True
    )
    connected = conn.connect(ip, 445)

    if not connected:
        raise ConnectionError(f"Could not connect to Seestar at {ip} via SMB")

    return conn


@multiple_ips
def list_folders() -> Dict[str, int]:
    """
    List all observation folders stored on the Seestar's internal eMMC.

    Each observation session creates a folder under ``MyWorks`` (e.g.
    ``"M 81"``, ``"Lunar"``).  This function returns every folder
    together with the number of album entries it contains (i.e. stacked
    results, not individual files).  Use :func:`list_folder_contents` to
    get the actual file listing.

    Returns
    -------
    dict of {str: int}
        Mapping of folder names to the number of album entries they
        contain.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.list_folders()
        {'M 81': 1, 'M 81_sub': 2053, 'Lunar': 2}

    """
    response = get_albums()
    summary = {}
    for group in response.get("result", {}).get("list", []):
        for entry in group.get("files", []):
            summary[entry["name"]] = entry["count"]
    return summary


@multiple_ips
def list_folder_contents(folder: str, filetype: str = "*") -> Dict[str, int]:
    """
    List every file inside an observation folder on the Seestar's eMMC.

    Uses the paginated JSON-RPC file listing API (port 4700), which is
    significantly faster than the previous SMB-based approach.

    Parameters
    ----------
    folder : str
        Name of the folder under ``MyWorks`` to list (e.g. ``"M 81_sub"``).
    filetype : str, optional
        Filter files by type. One of:

        - ``"*"`` — all files (default)
        - ``"fit"`` — FITS files only (``.fit``)
        - ``"jpg"`` — full-size JPEGs only (excludes thumbnails)
        - ``"thn.jpg"`` — thumbnail JPEGs only (``_thn.jpg``)
        - ``"*jpg"`` — all JPEGs (full-size and thumbnails)

    Returns
    -------
    dict of {str: int}
        Mapping of file names to their sizes in bytes.

    Examples
    --------

        >>> from seestarpy import data
        >>> files = data.list_folder_contents("M 81_sub", filetype="fit")
        >>> for name, size in list(files.items())[:3]:
        ...     print(f"{name}: {size / 1024:.0f} KB")
        Light_M 81_10.0s_IRCUT_20250607-221746.fit: 4050 KB
        Light_M 81_10.0s_IRCUT_20250607-221758.fit: 4050 KB
        Light_M 81_10.0s_IRCUT_20250607-221810.fit: 4050 KB

    """
    _valid = {"*", "fit", "jpg", "thn.jpg", "*jpg"}
    if filetype not in _valid:
        raise ValueError(f"filetype must be one of {_valid}, got {filetype!r}")

    # Step 1: Set directory context and get total page count
    response = get_img_file_page_number(f"{ROOT_DIR}/{folder}")
    total_pages = response.get("result", 0)
    if not isinstance(total_pages, int) or total_pages <= 0:
        return {}

    # Step 2: Fetch all pages
    contents = {}
    for page in range(total_pages):
        page_response = get_img_file_page_name(page)
        entries = page_response.get("result", [])
        if not isinstance(entries, list):
            continue

        for entry in entries:
            if entry.get("is_dir", False):
                continue
            name = entry.get("name", "")
            if not name:
                continue

            # Apply filetype filter
            if filetype == "*":
                pass
            elif filetype == "fit":
                if not name.endswith(".fit"):
                    continue
            elif filetype == "thn.jpg":
                if not name.endswith("_thn.jpg"):
                    continue
            elif filetype == "*jpg":
                if not name.endswith(".jpg"):
                    continue
            elif filetype == "jpg":
                if not name.endswith(".jpg") or name.endswith("_thn.jpg"):
                    continue

            # Convert KB to bytes for backward compatibility
            contents[name] = entry.get("size_k", 0) * 1024

    return contents


@multiple_ips
def delete_folder(folder: str) -> None:
    """
    Recursively delete an observation folder and all its files via SMB.

    .. warning::
        This permanently removes data from the Seestar's internal eMMC
        storage. There is no undo.

    Parameters
    ----------
    folder : str
        Name of the folder under ``MyWorks`` to delete (e.g.
        ``"M 81_sub"``).

    Examples
    --------

        >>> from seestarpy import data
        >>> data.list_folders()
        {'M 81': 3, 'M 81_sub': 37, 'Lunar': 2}
        >>> data.delete_folder("M 81_sub")
        >>> data.list_folders()
        {'M 81': 3, 'Lunar': 2}

    """
    conn = _connect_smb()

    try:
        path = f"{ROOT_DIR}/{folder}"
        entries = conn.listPath(SHARE_NAME, path)

        for entry in entries:
            if entry.filename in {".", ".."}:
                continue

            full_path = f"{path}/{entry.filename}"
            if entry.isDirectory:
                _delete_folder_recursive(conn, f"{folder}/{entry.filename}")
            else:
                conn.deleteFiles(SHARE_NAME, full_path)

        conn.deleteDirectory(SHARE_NAME, path)
    except OperationFailure:
        pass
    finally:
        conn.close()


def _delete_folder_recursive(conn: SMBConnection, folder: str) -> None:
    """Recursively delete a subfolder using an existing SMB connection."""
    path = f"{ROOT_DIR}/{folder}"
    entries = conn.listPath(SHARE_NAME, path)

    for entry in entries:
        if entry.filename in {".", ".."}:
            continue

        full_path = f"{path}/{entry.filename}"
        if entry.isDirectory:
            _delete_folder_recursive(conn, f"{folder}/{entry.filename}")
        else:
            conn.deleteFiles(SHARE_NAME, full_path)

    conn.deleteDirectory(SHARE_NAME, path)


@multiple_ips
def delete_files(folder: str, filenames: list[str]) -> dict[str, bool]:
    """
    Delete specific files from an observation folder via SMB.

    .. warning::
        This permanently removes data from the Seestar's internal eMMC
        storage. There is no undo.

    Parameters
    ----------
    folder : str
        Name of the folder under ``MyWorks`` (e.g. ``"M 81"``).
    filenames : list of str
        File names to delete within the folder.

    Returns
    -------
    dict of {str: bool}
        Mapping of each filename to ``True`` if deleted successfully,
        ``False`` if the file was not found or deletion failed.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.delete_files("M 81", ["old_stack.fit", "old_stack.jpg"])
        {'old_stack.fit': True, 'old_stack.jpg': True}

    """
    results = {}
    conn = _connect_smb()
    try:
        for fname in filenames:
            remote_path = f"{ROOT_DIR}/{folder}/{fname}"
            try:
                conn.deleteFiles(SHARE_NAME, remote_path)
                results[fname] = True
            except OperationFailure:
                results[fname] = False
    finally:
        conn.close()
    return results


def _build_http_url(remote_path):
    """Build an HTTP URL for a file on the Seestar's built-in web server.

    Parameters
    ----------
    remote_path : str
        Path relative to the HTTP root, e.g. ``"MyWorks/M 81/file.fit"``.

    Returns
    -------
    str
        Full URL like ``"http://192.168.1.246/MyWorks/M%2081/file.fit"``.
    """
    path = urllib.parse.quote(remote_path, safe="/")
    return f"http://{connection.DEFAULT_IP}/{path}"


@multiple_ips
def download_file(folder: str, filename: str, dest: str = ".") -> str:
    """Download a single file from the Seestar via HTTP.

    The Seestar runs an HTTP file server on port 80.  This function
    streams the file to a local directory in 64 KB chunks.

    Parameters
    ----------
    folder : str
        Folder under ``MyWorks``, e.g. ``"M 81"`` or ``"M 81_sub"``.
    filename : str
        Name of the file to download, e.g.
        ``"DSO_Stacked_33_M 81_20.0s_20260311_213509.fit"``.
    dest : str
        Local directory to save the file in.  Created if it doesn't
        exist.  Default ``"."``.

    Returns
    -------
    str
        Absolute path to the downloaded file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist on the Seestar (HTTP 404).
    ConnectionError
        If the Seestar cannot be reached or another HTTP error occurs.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.download_file("M 81", "DSO_Stacked_33_M 81_20.0s_20260311_213509.fit")
        './DSO_Stacked_33_M 81_20.0s_20260311_213509.fit'

    """
    url = _build_http_url(f"{ROOT_DIR}/{folder}/{filename}")
    os.makedirs(dest, exist_ok=True)
    local_path = os.path.join(dest, filename)

    try:
        resp = urllib.request.urlopen(url, timeout=30)
        total = 0
        with open(local_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
        print(f"  {filename} ({total / 1024 / 1024:.2f} MB) OK")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(
                f"File not found on Seestar: {folder}/{filename}"
            ) from exc
        raise ConnectionError(
            f"HTTP {exc.code} downloading {folder}/{filename}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach Seestar: {exc.reason}"
        ) from exc

    return os.path.abspath(local_path)


@multiple_ips
def download_folder(folder: str = "", dest: str = "") -> None:
    """
    Download an entire observation folder from the Seestar's eMMC via SMB.

    Copies every file from the given folder under ``MyWorks`` to a local
    directory.  Progress is printed to stdout as each file completes.

    Parameters
    ----------
    folder : str
        Name of the folder under ``MyWorks`` to download (e.g.
        ``"M 81_sub"``).
    dest : str
        Local directory where the folder will be saved.  Created
        automatically if it does not exist.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.download_folder("M 81_sub", dest="/home/user/astro")
        Downloading 37 files from 'M 81_sub' (150.0 MB)...
          [1/37] Light_M 81_10.0s_IRCUT_20250607-221746.fit (4.05 MB) OK
          ...
        OK Download complete: 37 files

    """
    os.makedirs(dest, exist_ok=True)

    # List files and download each one using SMB
    files = list_folder_contents(folder)
    folder_dest = os.path.join(dest, folder)
    os.makedirs(folder_dest, exist_ok=True)

    total_files = len(files)
    total_size = sum(files.values())
    print(
        f"Downloading {total_files} files from '{folder}' ({total_size / 1024 / 1024:.1f} MB)...")

    conn = _connect_smb()
    try:
        for idx, (fname, fsize) in enumerate(files.items(), 1):
            remote_path = f"{ROOT_DIR}/{folder}/{fname}"
            local_path = os.path.join(folder_dest, fname)
            print(
                f"  [{idx}/{total_files}] {fname} ({fsize / 1024 / 1024:.2f} MB)",
                end="", flush=True)
            with open(local_path, "wb") as f:
                conn.retrieveFile(SHARE_NAME, remote_path, f)
            print(" OK")
        print(f"OK Download complete: {total_files} files")
    finally:
        conn.close()
