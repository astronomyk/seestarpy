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
    """Create and return an SMBConnection using direct TCP (445)."""

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
    """List all folders under MyWorks and return file counts per folder."""
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
    """List files inside a specific folder under MyWorks."""
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
    """Delete a folder and all its contents using SMB."""
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
    """Download an entire folder from MyWorks using SMB."""
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
