import os
import re
from collections import defaultdict
import subprocess
from datetime import datetime, timedelta
from tqdm import tqdm
from time import sleep

SMB_SHARE = "//seestar/EMMC Images"
ROOT_FOLDER = "MyWorks"


def run_smb_ls(path):
    cmd = ["smbclient", SMB_SHARE, "-N", "-c", f"cd {path}; ls"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip().splitlines()


def parse_ls_output(lines):
    files = []
    folders = []

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 8:
            continue  # not enough data to parse

        name = parts[0]
        date_str = " ".join(parts[-5:])  # Last 5 parts: 'Thu May  1 22:27:38 2025'

        try:
            dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
        except ValueError:
            continue

        if parts[1] == "D":
            folders.append(name)
        else:
            files.append({"name": name, "date": dt.strftime("%Y-%m-%d %H:%M:%S")})

    return folders, files


def crawl_folder(path, verbose=False):
    try:
        output = run_smb_ls(path)
        if verbose:
            print(f"\n📂 Contents of {path}:")
            print("\n".join(output))

        folders, files = parse_ls_output(output)

        result = {
            "files": files,
            "subfolders": {}
        }

        for folder in folders:
            if folder in [".", ".."]:
                continue
            full_path = f"{path}/{folder}"
            result["subfolders"][folder] = crawl_folder(full_path)

        return result

    except subprocess.CalledProcessError as e:
        print(f"❌ Error reading {path}: {e.stderr or e.stdout}")
        return {}


def crawl_seestar():
    try:
        # List top-level folders under MyWorks
        top_level_output = run_smb_ls("MyWorks")
        folder_names, _ = parse_ls_output(top_level_output)

        all_data = {}

        for folder in folder_names:
            if folder in [".", "..", "System Volume Information"]:
                continue
            full_path = f"MyWorks/{folder}"
            all_data[folder] = crawl_folder(full_path)

        return all_data

    except Exception as e:
        print("❌ Error crawling seestar folders:", e)
        return {}


def get_targets_with_recent_fits(crawl_data, hours=12):
    """Return top-level targets with .fits files newer than N hours ago."""

    cutoff = datetime.now() - timedelta(hours=hours)
    recent_targets = []

    for target, content in crawl_data.items():
        has_recent = False

        # Top-level FITS files
        for f in content.get("files", []):
            if f["name"].lower().endswith((".fits", ".fit")):
                dt = datetime.strptime(f["date"], "%Y-%m-%d %H:%M:%S")
                if dt > cutoff:
                    has_recent = True
                    break

        # Subfolder FITS files
        if not has_recent:
            for subfolder, subcontent in content.get("subfolders", {}).items():
                for f in subcontent.get("files", []):
                    if f["name"].lower().endswith((".fits", ".fit")):
                        dt = datetime.strptime(f["date"], "%Y-%m-%d %H:%M:%S")
                        if dt > cutoff:
                            has_recent = True
                            break
                if has_recent:
                    break

        if has_recent:
            recent_targets.append(target)

    return recent_targets


def _sync_folder(parent_path, current_folder, content, dest_root):
    remote_path = f"{parent_path}/{current_folder}"
    local_path = os.path.join(dest_root, current_folder)

    os.makedirs(local_path, exist_ok=True)

    # Sync files in this folder
    for f in content.get("files", []):
        filename = f["name"]
        if not filename.lower().endswith((".fits", ".fit")):
            continue

        local_file_path = os.path.join(local_path, filename)
        if os.path.exists(local_file_path):
            continue  # already synced

        # SMB get command
        try:
            smb_cmd = [
                "smbclient",
                "//seestar/EMMC Images",
                "-N",
                "-c",
                f'cd "{remote_path}"; get "{filename}" "{local_file_path}"'
            ]
            print(f"⬇️  Downloading: {remote_path}/{filename} → {local_file_path}")
            subprocess.run(smb_cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to download {filename} from {remote_path}: {e.stderr or e.stdout}")

    # Recurse into subfolders
    for subfolder_name, subfolder_content in content.get("subfolders", {}).items():
        _sync_folder(remote_path, subfolder_name, subfolder_content, local_path)


def sync_fits_files_to_local(crawl_data, dest_root):
    # First count how many files we'll download
    download_list = []

    for top_folder, content in crawl_data.items():
        _gather_downloads("MyWorks", top_folder, content, dest_root, download_list)

    # Now actually download them with a progress bar
    with tqdm(total=len(download_list), desc="Downloading FITS files") as pbar:
        for item in download_list:
            remote_path, filename, local_file_path = item

            try:
                smb_cmd = [
                    "smbclient",
                    "//seestar/EMMC Images",
                    "-N",
                    "-c",
                    f'cd "{remote_path}"; get "{filename}" "{local_file_path}"'
                ]
                subprocess.run(smb_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                tqdm.write(f"❌ Failed to download {remote_path}/{filename}")
            pbar.update(1)


def _gather_downloads(parent_path, current_folder, content, dest_root, download_list):
    remote_path = f"{parent_path}/{current_folder}"
    local_path = os.path.join(dest_root, current_folder)

    os.makedirs(local_path, exist_ok=True)

    for f in content.get("files", []):
        filename = f["name"]
        if not filename.lower().endswith((".fits", ".fit")):
            continue

        local_file_path = os.path.join(local_path, filename)
        if not os.path.exists(local_file_path):
            download_list.append((remote_path, filename, local_file_path))

    for subfolder_name, subfolder_content in content.get("subfolders", {}).items():
        _gather_downloads(remote_path, subfolder_name, subfolder_content, local_path, download_list)


def crawl_local_archive_by_night(archive_root):
    night_data = defaultdict(lambda: defaultdict(int))

    # Regex to extract datetime from filename
    pattern = re.compile(r"(\d{8})-(\d{6})")  # Matches 20250429-232613

    for root, dirs, files in os.walk(archive_root):
        for fname in files:
            if not fname.lower().endswith((".fits", ".fit")):
                continue

            match = pattern.search(fname)
            if not match:
                continue

            date_str, time_str = match.groups()
            try:
                dt = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
            except ValueError:
                continue

            # Determine observing "night" based on midday boundaries
            if dt.hour < 12:
                observing_date = (dt - timedelta(days=1)).date()
            else:
                observing_date = dt.date()

            # Target is the folder name immediately under archive root
            rel_path = os.path.relpath(root, archive_root)
            target = rel_path.split(os.sep)[0]

            night_data[target][str(observing_date)] += 1

    return night_data
