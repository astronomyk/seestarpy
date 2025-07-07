import os
from smb.SMBConnection import SMBConnection

from connection import DEFAULT_IP, VERBOSE_LEVEL


def list_contents(folder=None, ip_override=None):
    ip = DEFAULT_IP if ip_override is None else ip_override

    conn = SMBConnection('', '', 'windows_pc', 'seestar', use_ntlm_v2=True)
    connected = conn.connect(ip, 139)
    if not connected:
        print(f"❌ Could not connect to Seestar at {ip}")
        return {}

    summary = {}

    entries = conn.listPath('EMMC Images', 'MyWorks')

    if not folder:
        print("📂 Folders in MyWorks:")
        for entry in entries:
            if entry.isDirectory and entry.filename not in ['.', '..']:
                folder_name = entry.filename
                # Count files inside this folder
                count = sum(
                    1 for f in
                    conn.listPath('EMMC Images', f"MyWorks/{folder_name}")
                    if not f.isDirectory and f.filename not in ['.', '..']
                )
                summary[folder_name] = count
                if VERBOSE_LEVEL >= 1: print(f" - {folder_name} ({count} files)")
    else:
        # Look for folder match
        found = False
        for entry in entries:
            if entry.isDirectory and entry.filename == folder:
                found = True
                print(f"📁 Files in MyWorks/{folder}:")
                sub_entries = conn.listPath('EMMC Images', f"MyWorks/{folder}")
                for sub in sub_entries:
                    if sub.filename not in ['.', '..'] and not sub.isDirectory:
                        summary[sub.filename] = sub.file_size
                        if VERBOSE_LEVEL >= 1: print(f" - {sub.filename} ({sub.file_size} bytes)")
                break
        if not found:
            if VERBOSE_LEVEL >= 1: print(f"🚫 Folder '{folder}' not found in MyWorks.")

    conn.close()
    return summary


def download_contents(folder=None, local_base=None, file_types=None, ip_override=None):
    ip = DEFAULT_IP if ip_override is None else ip_override

    local_base = local_base or os.path.expanduser('~/seestar_downloads')
    file_types = file_types or [".fit"]

    conn = SMBConnection('', '', 'windows_pc', 'seestar', use_ntlm_v2=True)
    connected = conn.connect(ip, 139)
    if not connected:
        print(f"❌ Could not connect to Seestar at {ip}")
        return

    entries = conn.listPath('EMMC Images', 'MyWorks')

    if not folder:
        # Copy all folders under MyWorks
        for entry in entries:
            if entry.isDirectory and entry.filename not in ['.', '..']:
                copy_folder_contents(conn, entry.filename, local_base, file_types)
    else:
        # Look for that specific folder on Seestar
        found = False
        for entry in entries:
            if entry.isDirectory and entry.filename == folder:
                found = True
                copy_folder_contents(conn, entry.filename, local_base, file_types)
                break
        if not found:
            print(f"🚫 Folder '{folder}' not found on Seestar.")

    conn.close()


def copy_folder_contents(conn, remote_folder, local_base, file_types):
    remote_path = f"MyWorks/{remote_folder}"
    local_path = os.path.join(local_base, remote_folder)
    os.makedirs(local_path, exist_ok=True)

    print(f"🔄 Syncing folder: {remote_folder} with file types {file_types}")

    local_files = set(os.listdir(local_path))

    remote_files = conn.listPath('EMMC Images', remote_path)
    for file in remote_files:
        if file.isDirectory or file.filename in ['.', '..']:
            continue

        # Check extension filter
        if not should_download(file.filename, file_types):
            continue

        if file.filename not in local_files:
            local_file_path = os.path.join(local_path, file.filename)
            with open(local_file_path, 'wb') as f:
                conn.retrieveFile('EMMC Images', f"{remote_path}/{file.filename}", f)
            print(f"✅ Downloaded: {remote_folder}/{file.filename}")
        else:
            print(f"✔️ Skipped (already exists): {remote_folder}/{file.filename}")

def should_download(filename, file_types):
    if ".*" in file_types:
        return True
    for ext in file_types:
        if filename.lower().endswith(ext.lower()):
            return True
    return False


def delete_contents(folder=None, ip_override=None):
    ip = DEFAULT_IP if ip_override is None else ip_override
    if not folder:
        print("🚫 Please specify a folder name to delete.")
        return

    conn = SMBConnection('', '', 'windows_pc', 'seestar', use_ntlm_v2=True)
    connected = conn.connect(ip, 139)
    if not connected:
        print(f"❌ Could not connect to Seestar at {ip}")
        return

    remote_path = f"MyWorks/{folder}"

    # Check if folder exists
    try:
        conn.listPath('EMMC Images', remote_path)
    except Exception as e:
        print(f"🚫 Folder '{folder}' does not exist on Seestar.")
        conn.close()
        return

    # Delete files inside the folder
    try:
        files = conn.listPath('EMMC Images', remote_path)
        for file in files:
            if file.filename in ['.', '..']:
                continue
            if file.isDirectory:
                print(
                    f"⚠️ Nested directory '{file.filename}' detected, skipping (simple delete only handles single level).")
            else:
                file_path = f"{remote_path}/{file.filename}"
                conn.deleteFiles('EMMC Images', file_path)
                print(f"🗑️ Deleted file: {file.filename}")

        # Attempt to remove the empty folder
        conn.deleteDirectory('EMMC Images', remote_path)
        print(f"✅ Deleted folder '{folder}' from Seestar.")

    except Exception as e:
        print(f"❌ Error while deleting folder: {e}")

    conn.close()


# Usage examples:
# print(list_contents())  # list folders only
print(list_contents(folder="M 81"))  # list files inside MyWorks/M42 if exists

# Usage examples:
# download_contents(local_base="E:/seestar_downloads")               # downloads all folders under MyWorks
# download_contents(folder="Mizar_sub", local_base="E:/seestar_downloads", file_types=["thn.jpg"])   # only downloads missing files under MyWorks/M42

# Usage example:
# delete_contents(folder="Mizar_sub")