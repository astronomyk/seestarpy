"""CrowdSky web API client for uploading and downloading stacked FITS files.

This module wraps the CrowdSky server's HTTP Basic Auth endpoints:

- **GET /api/my_stacks.php** — list user's uploaded stacks
- **POST /api/upload_stack.php** — upload a stacked FITS file
- **GET /api/download_stack.php** — download a stacked FITS by chunk_key

Credentials can be set via environment variables (``CROWDSKY_USERNAME``,
``CROWDSKY_PASSWORD``) or at runtime with :func:`set_credentials`.

Example::

    from seestarpy.crowdsky import server

    server.set_credentials("alice", "s3cret")
    stacks = server.list_stacks()
    server.upload_stack("CrowdSky_38_M81_20.0s_LP_20260227-224500.fit")
    server.download_stack("abc123", dest="./downloads")
"""

import os
from pathlib import Path

import requests

BASE_URL = "https://crowdsky.univie.ac.at"
USERNAME = os.environ.get("CROWDSKY_USERNAME", "")
PASSWORD = os.environ.get("CROWDSKY_PASSWORD", "")


def set_credentials(username, password):
    """Set CrowdSky login credentials for the session.

    Parameters
    ----------
    username : str
        CrowdSky account username.
    password : str
        CrowdSky account password.
    """
    global USERNAME, PASSWORD
    USERNAME = username
    PASSWORD = password


def set_base_url(url):
    """Override the CrowdSky server URL (for testing or staging).

    Parameters
    ----------
    url : str
        Base URL without trailing slash, e.g. ``"https://staging.crowdsky.example.com"``.
    """
    global BASE_URL
    BASE_URL = url.rstrip("/")


def _get_auth():
    """Return (username, password) tuple; raise if not configured."""
    if not USERNAME or not PASSWORD:
        raise RuntimeError(
            "CrowdSky credentials not set. Call set_credentials() or set "
            "CROWDSKY_USERNAME and CROWDSKY_PASSWORD environment variables."
        )
    return (USERNAME, PASSWORD)


def _request(method, endpoint, **kwargs):
    """Send an authenticated request to the CrowdSky API.

    Injects HTTP Basic Auth, prepends BASE_URL, sets a 30s timeout,
    and translates 401 responses into a clear RuntimeError.
    """
    url = f"{BASE_URL}{endpoint}"
    kwargs.setdefault("timeout", 30)
    kwargs["auth"] = _get_auth()

    resp = requests.request(method, url, **kwargs)

    if resp.status_code == 401:
        raise RuntimeError("CrowdSky authentication failed (401).")
    resp.raise_for_status()

    return resp


def list_stacks(object_name=None):
    """List the user's uploaded stacks on the CrowdSky server.

    Parameters
    ----------
    object_name : str, optional
        Filter results by object name (passed as ``?object=`` query param).

    Returns
    -------
    list[dict]
        Each dict contains server-side metadata such as ``chunk_key``,
        ``object_name``, ``n_frames``, etc.
    """
    params = {}
    if object_name is not None:
        params["object"] = object_name

    resp = _request("GET", "/api/my_stacks.php", params=params)
    return resp.json()


def upload_stack(fits_path, thumbnail=None, n_frames_input=None,
                 n_frames_aligned=None, date_obs_start=None,
                 date_obs_end=None):
    """Upload a stacked FITS file to the CrowdSky server.

    Parameters
    ----------
    fits_path : str or Path
        Local path to the ``.fit`` / ``.fits`` file.
    thumbnail : str or Path, optional
        Local path to a thumbnail image (JPEG/PNG).
    n_frames_input : int, optional
        Total number of input sub-frames.
    n_frames_aligned : int, optional
        Number of frames that were successfully aligned.
    date_obs_start : str, optional
        ISO 8601 timestamp of the first sub-frame.
    date_obs_end : str, optional
        ISO 8601 timestamp of the last sub-frame.

    Returns
    -------
    dict
        Server response with keys like ``ok``, ``stack_id``, ``chunk_key``,
        ``telescope_id``.

    Raises
    ------
    FileNotFoundError
        If *fits_path* does not exist.
    """
    fits_path = Path(fits_path)
    if not fits_path.exists():
        raise FileNotFoundError(f"FITS file not found: {fits_path}")

    files = {"fits_file": (fits_path.name, fits_path.open("rb"))}
    if thumbnail is not None:
        thumb_path = Path(thumbnail)
        files["thumbnail"] = (thumb_path.name, thumb_path.open("rb"))

    data = {}
    if n_frames_input is not None:
        data["n_frames_input"] = str(n_frames_input)
    if n_frames_aligned is not None:
        data["n_frames_aligned"] = str(n_frames_aligned)
    if date_obs_start is not None:
        data["date_obs_start"] = date_obs_start
    if date_obs_end is not None:
        data["date_obs_end"] = date_obs_end

    resp = _request("POST", "/api/upload_stack.php", files=files, data=data)
    return resp.json()


def download_stack(chunk_keys, dest="."):
    """Download stacked FITS files from the CrowdSky server by chunk key.

    Parameters
    ----------
    chunk_keys : str or list[str]
        One or more chunk keys to download.
    dest : str or Path
        Destination directory.  Defaults to current directory.

    Returns
    -------
    list[Path]
        List of local file paths that were downloaded.
    """
    if isinstance(chunk_keys, str):
        chunk_keys = [chunk_keys]

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for key in chunk_keys:
        resp = _request(
            "GET", "/api/download_stack.php", params={"chunk_key": key},
            stream=True,
        )

        # Derive filename from Content-Disposition header or chunk key
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            fname = cd.split("filename=")[-1].strip('"')
        else:
            fname = f"{key}.fits"

        out_path = dest / fname
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        downloaded.append(out_path)

    return downloaded
