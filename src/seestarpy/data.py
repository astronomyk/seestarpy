# seestar_smb_utils.py
# Utilities for listing, deleting, and downloading data from a Seestar S50
# Listing/deleting uses pysmb over direct SMB (port 445)
# Downloading uses mounted SMB paths on Unix; Windows uses native SMB paths

import os
from typing import Dict

from smb.SMBConnection import SMBConnection
from .connection import DEFAULT_IP

SHARE_NAME = "EMMC Images"
ROOT_DIR = "MyWorks"


def _connect_smb(ip: str = DEFAULT_IP) -> SMBConnection:
    """
    Create and return an SMBConnection using direct TCP (port 445).

    Parameters
    ----------
    ip : str, optional
        IP address of the Seestar. Defaults to :data:`connection.DEFAULT_IP`.

    Returns
    -------
    SMBConnection
        An open SMB connection to the Seestar.

    Raises
    ------
    ConnectionError
        If the connection to the Seestar fails.
    """

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


def list_folders(ip: str = DEFAULT_IP) -> Dict[str, int]:
    """
    List all observation folders stored on the Seestar's internal eMMC.

    Each observation session creates a folder under ``MyWorks`` (e.g.
    ``"M 81"``, ``"Lunar"``).  This function returns every folder
    together with a count of the files it contains.

    Parameters
    ----------
    ip : str, optional
        IP address of the Seestar. Defaults to :data:`connection.DEFAULT_IP`.

    Returns
    -------
    dict of {str: int}
        Mapping of folder names to the number of files they contain.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.list_folders()
        {'M 81': 3, 'M 81_sub': 37, 'Lunar': 2}

    """
    conn = _connect_smb(ip)
    summary = {}

    try:
        entries = conn.listPath(SHARE_NAME, ROOT_DIR)
        for entry in entries:
            if entry.isDirectory and entry.filename not in {".", ".."}:
                folder = entry.filename
                files = conn.listPath(SHARE_NAME, f"{ROOT_DIR}/{folder}")
                count = sum(
                    1 for f in files if not f.isDirectory and f.filename not in {".", ".."}
                )
                summary[folder] = count
    finally:
        conn.close()

    return summary


def list_folder_contents(folder: str, ip: str = DEFAULT_IP) -> Dict[str, int]:
    """
    List every file inside an observation folder on the Seestar's eMMC.

    Parameters
    ----------
    folder : str
        Name of the folder under ``MyWorks`` to list (e.g. ``"M 81_sub"``).
    ip : str, optional
        IP address of the Seestar. Defaults to :data:`connection.DEFAULT_IP`.

    Returns
    -------
    dict of {str: int}
        Mapping of file names to their sizes in bytes.

    Examples
    --------

        >>> from seestarpy import data
        >>> files = data.list_folder_contents("M 81_sub")
        >>> for name, size in list(files.items())[:3]:
        ...     print(f"{name}: {size / 1024:.0f} KB")
        Light_M 81_10.0s_IRCUT_20250607-221746.fit: 4050 KB
        Light_M 81_10.0s_IRCUT_20250607-221758.fit: 4050 KB
        Light_M 81_10.0s_IRCUT_20250607-221810.fit: 4050 KB

    """
    conn = _connect_smb(ip)
    contents = {}

    try:
        entries = conn.listPath(SHARE_NAME, f"{ROOT_DIR}/{folder}")
        for entry in entries:
            if not entry.isDirectory and entry.filename not in {".", ".."}:
                contents[entry.filename] = entry.file_size
    finally:
        conn.close()

    return contents


def delete_folder(folder: str, ip: str = DEFAULT_IP) -> None:
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
    ip : str, optional
        IP address of the Seestar. Defaults to :data:`connection.DEFAULT_IP`.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.list_folders()
        {'M 81': 3, 'M 81_sub': 37, 'Lunar': 2}
        >>> data.delete_folder("M 81_sub")
        >>> data.list_folders()
        {'M 81': 3, 'Lunar': 2}

    """
    conn = _connect_smb(ip)

    try:
        path = f"{ROOT_DIR}/{folder}"
        entries = conn.listPath(SHARE_NAME, path)

        for entry in entries:
            if entry.filename in {".", ".."}:
                continue

            full_path = f"{path}/{entry.filename}"
            if entry.isDirectory:
                # recursive delete
                delete_folder(f"{folder}/{entry.filename}", ip)
            else:
                conn.deleteFiles(SHARE_NAME, full_path)

        conn.deleteDirectory(SHARE_NAME, path)
    finally:
        conn.close()


def download_folder(folder: str = "", dest: str = "",
                    ip: str = DEFAULT_IP) -> None:
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
    ip : str, optional
        IP address of the Seestar. Defaults to :data:`connection.DEFAULT_IP`.

    Examples
    --------

        >>> from seestarpy import data
        >>> data.download_folder("M 81_sub", dest="/home/user/astro")
        Downloading 37 files from 'M 81_sub' (150.0 MB)...
          [1/37] Light_M 81_10.0s_IRCUT_20250607-221746.fit (4.05 MB) ✓
          ...
        ✓ Download complete: 37 files

    """
    os.makedirs(dest, exist_ok=True)

    # List files and download each one using SMB
    files = list_folder_contents(folder, ip)
    folder_dest = os.path.join(dest, folder)
    os.makedirs(folder_dest, exist_ok=True)

    total_files = len(files)
    total_size = sum(files.values())
    print(
        f"📁 Downloading {total_files} files from '{folder}' ({total_size / 1024 / 1024:.1f} MB)...")

    conn = _connect_smb(ip)
    try:
        for idx, (fname, fsize) in enumerate(files.items(), 1):
            remote_path = f"{ROOT_DIR}/{folder}/{fname}"
            local_path = os.path.join(folder_dest, fname)
            print(
                f"  [{idx}/{total_files}] {fname} ({fsize / 1024 / 1024:.2f} MB)",
                end="", flush=True)
            with open(local_path, "wb") as f:
                conn.retrieveFile(SHARE_NAME, remote_path, f)
            print(" ✓")
        print(f"✓ Download complete: {total_files} files")
    finally:
        conn.close()
