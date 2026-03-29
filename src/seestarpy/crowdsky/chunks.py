"""CrowdSky time-block stacking for citizen-science time-domain astronomy.

This module automates the production of fixed-duration stacked chunks from
a Seestar observation session.  Raw sub-frames are grouped into
clock-aligned time blocks (default 15 minutes), and each block is
batch-stacked independently.  Output files are renamed to a ``CrowdSky_*``
naming convention that encodes the block boundary timestamp and filter,
enabling deterministic idempotent re-runs.

Typical workflow::

    from seestarpy import crowdsky

    # 1. See what's on the Seestar
    crowdsky.list_targets()

    # 2. Preview unstacked blocks for one target
    crowdsky.stack_blocks("M 81", dry_run=True)

    # 3. Stack one target
    crowdsky.stack_blocks("M 81")

    # 4. Or stack everything at once
    crowdsky.stack_all(dry_run=True)   # preview
    crowdsky.stack_all()               # run
"""

import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tzlocal import get_localzone

from .. import data
from ..connection import multiple_ips
from ..stack import (
    clear_batch_stack,
    get_batch_stack_status,
    set_batch_stack_setting,
    start_batch_stack,
)
from .healpix import radec_to_healpix

LIGHT_RE = re.compile(
    r"^Light_(.+)_(\d+\.\d+s)_([A-Za-z]+)_(\d{8}-\d{6})\.fit$"
)
_DSO_STACKED_RE = re.compile(
    r"^DSO_Stacked_(\d+)_(.+)_(\d+\.\d+s)_(\d{8})_(\d{6})\.fit$"
)
# CrowdSky output files encode a UTC chunk key and HEALPix pixel:
#   CrowdSky_<N>_<target>_<exposure>_<filter>_<YYYYMMDD.CC>_HP<nnnnnn>.fit
CROWDSKY_RE = re.compile(
    r"^CrowdSky_(\d+)_(.+)_(\d+\.\d+s)_([A-Za-z]+)_(\d{8}\.\d{1,2})_HP(\d{6})\.fit$"
)
# Legacy format (pre-HEALPix): CrowdSky_<N>_<target>_<exp>_<filt>_<YYYYMMDD-HHMMSS>.fit
CROWDSKY_RE_LEGACY = re.compile(
    r"^CrowdSky_(\d+)_(.+)_(\d+\.\d+s)_([A-Za-z]+)_(\d{8}-\d{6})\.fit$"
)

# Backward-compat aliases
_LIGHT_RE = LIGHT_RE
_CROWDSKY_RE = CROWDSKY_RE
_CROWDSKY_RE_LEGACY = CROWDSKY_RE_LEGACY


def parse_light_filename(filename):
    """Parse a raw light frame filename into its components.

    Parameters
    ----------
    filename : str
        e.g. ``"Light_M 81_20.0s_LP_20260227-225203.fit"``

    Returns
    -------
    dict or None
        Dict with keys ``target``, ``exposure``, ``filter``, ``datetime``.
        Returns ``None`` if the filename doesn't match the expected pattern.

    Examples
    --------
    ::

        >>> parse_light_filename("Light_M 81_20.0s_LP_20260227-225203.fit")
        {'target': 'M 81', 'exposure': '20.0s', 'filter': 'LP',
         'datetime': datetime(2026, 2, 27, 22, 52, 3)}

    """
    m = LIGHT_RE.match(filename)
    if not m:
        return None
    return {
        "target": m.group(1),
        "exposure": m.group(2),
        "filter": m.group(3),
        "datetime": datetime.strptime(m.group(4), "%Y%m%d-%H%M%S"),
    }


# Backward-compat alias
_parse_light_filename = parse_light_filename


def _floor_to_block(dt, block_minutes):
    """Floor a datetime to the nearest block boundary."""
    return dt.replace(
        minute=(dt.minute // block_minutes) * block_minutes,
        second=0,
        microsecond=0,
    )


def _read_fits_ra_dec(remote_path):
    """Read RA/Dec from a FITS header on the Seestar via HTTP Range request.

    Fetches the first 5760 bytes (two FITS header blocks of 2880 bytes each)
    and parses 80-byte FITS cards for ``RA`` and ``DEC`` keywords.

    Parameters
    ----------
    remote_path : str
        Path relative to the HTTP root, e.g. ``"MyWorks/M 81/file.fit"``.

    Returns ``(ra_deg, dec_deg)`` or ``(None, None)`` on failure.
    """
    try:
        from .. import connection

        path = urllib.parse.quote(remote_path, safe="/")
        url = f"http://{connection.DEFAULT_IP}/{path}"
        req = urllib.request.Request(url, headers={"Range": "bytes=0-5759"})
        resp = urllib.request.urlopen(req, timeout=10)
        header_bytes = resp.read().decode("ascii", errors="replace")
        ra = dec = None
        for i in range(0, len(header_bytes), 80):
            card = header_bytes[i : i + 80]
            if card.startswith("RA      ="):
                ra = float(card.split("=")[1].split("/")[0].strip())
            elif card.startswith("DEC     ="):
                dec = float(card.split("=")[1].split("/")[0].strip())
            if ra is not None and dec is not None:
                return (ra, dec)
    except Exception:
        pass
    return (None, None)


def local_dt_to_chunk_str(dt_local):
    """Convert a naive local datetime to a ``YYYYMMDD.CC`` UTC chunk string.

    ``CC`` is the 15-minute chunk index (0–95) within the UTC day.
    """
    local_tz = get_localzone()
    utc_dt = dt_local.replace(tzinfo=local_tz).astimezone(ZoneInfo("UTC"))
    date_str = utc_dt.strftime("%Y%m%d")
    chunk_index = (utc_dt.hour * 3600 + utc_dt.minute * 60) // 900
    return f"{date_str}.{chunk_index:02d}"


# Backward-compat alias
_local_dt_to_chunk_str = local_dt_to_chunk_str


def compute_chunk_key(block_start, ra_deg, dec_deg):
    """Build a CrowdSky chunk key from a local block start and sky position.

    Returns a string like ``"20250115.78_HP049152"``.
    """
    chunk_str = local_dt_to_chunk_str(block_start)
    if ra_deg is not None and dec_deg is not None:
        hp_str = f"HP{radec_to_healpix(ra_deg, dec_deg):06d}"
    else:
        hp_str = "HP000000"
    return f"{chunk_str}_{hp_str}"


# Backward-compat alias
_compute_chunk_key = compute_chunk_key


def _rename_output(target, block, status):
    """Rename a DSO_Stacked output to CrowdSky format with block metadata.

    Renames all three companion files (``.fit``, ``.jpg``, ``_thn.jpg``)
    produced by the batch stacker.  The CrowdSky filename encodes the
    block-start timestamp and filter so that :func:`find_unstacked_blocks`
    can do exact coverage matching.

    Returns the new ``.fit`` filename on success, or ``None`` on failure.
    """
    output_file = status.get("output_file", {})
    files = output_file.get("files", [])
    if not files:
        return None

    # Find the .fit output
    old_names = [f["name"] for f in files if f["name"].endswith(".fit")]
    if not old_names:
        return None
    old_fit = old_names[0]

    # Parse frame count from the DSO_Stacked filename
    m = _DSO_STACKED_RE.match(old_fit)
    frame_count = m.group(1) if m else str(block["frame_count"])

    old_stem = old_fit.removesuffix(".fit")
    folder = f"MyWorks/{target}"

    try:
        # Read RA/Dec via HTTP Range request (no SMB needed)
        ra, dec = _read_fits_ra_dec(f"{folder}/{old_fit}")
        chunk_key = compute_chunk_key(block["block_start"], ra, dec)

        new_stem = (
            f"CrowdSky_{frame_count}_{target}_{block['exposure']}"
            f"_{block['filter']}_{chunk_key}"
        )

        # SMB connection only needed for the rename operation
        conn = data._connect_smb()
        try:
            for ext in (".fit", ".jpg", "_thn.jpg"):
                conn.rename(
                    data.SHARE_NAME,
                    f"{folder}/{old_stem}{ext}",
                    f"{folder}/{new_stem}{ext}",
                )
        finally:
            conn.close()
        return f"{new_stem}.fit"
    except Exception:
        return None


def group_frames_into_blocks(parsed_frames, block_minutes=15):
    """Group parsed frame dicts into clock-aligned time blocks.

    Parameters
    ----------
    parsed_frames : list[dict]
        Each dict must have at least keys ``filename``, ``exposure``,
        ``filter``, ``datetime`` (as returned by :func:`parse_light_filename`
        with ``filename`` added).
    block_minutes : int
        Block duration in minutes.  Default 15.

    Returns
    -------
    dict
        Keyed by ``(block_start, exposure, filter)`` tuples.  Values are
        dicts with keys: ``block_start``, ``block_end``, ``exposure``,
        ``filter``, ``files`` (sorted list), ``frame_count``.
    """
    block_delta = timedelta(minutes=block_minutes)
    blocks = {}
    for p in parsed_frames:
        block_start = _floor_to_block(p["datetime"], block_minutes)
        key = (block_start, p["exposure"], p["filter"])
        if key not in blocks:
            blocks[key] = {
                "block_start": block_start,
                "block_end": block_start + block_delta,
                "exposure": p["exposure"],
                "filter": p["filter"],
                "files": [],
            }
        blocks[key]["files"].append(p["filename"])

    for block in blocks.values():
        block["files"].sort()
        block["frame_count"] = len(block["files"])

    return blocks


def parse_coverage_from_filenames(filenames):
    """Extract coverage tuples from ``CrowdSky_*`` filenames.

    Handles both the current format (with HEALPix pixel) and the legacy
    format (with local timestamp).

    Parameters
    ----------
    filenames : iterable of str
        Filenames to scan for ``CrowdSky_*`` patterns.

    Returns
    -------
    set[tuple[str, str, str]]
        Set of ``(chunk_str, exposure, filter)`` tuples representing
        blocks that are already covered.
    """
    covered = set()
    for fname in filenames:
        m = CROWDSKY_RE.match(fname)
        if m:
            covered.add((m.group(5), m.group(3), m.group(4)))
            continue
        m = CROWDSKY_RE_LEGACY.match(fname)
        if m:
            dt = datetime.strptime(m.group(5), "%Y%m%d-%H%M%S")
            covered.add((local_dt_to_chunk_str(dt), m.group(3), m.group(4)))
    return covered


def filter_covered_blocks(blocks, covered):
    """Remove blocks whose UTC chunk key is in the *covered* set.

    Parameters
    ----------
    blocks : dict
        As returned by :func:`group_frames_into_blocks`.
    covered : set[tuple[str, str, str]]
        ``(chunk_str, exposure, filter)`` tuples.

    Returns
    -------
    list[dict]
        Sorted list of uncovered block dicts.
    """
    sorted_keys = sorted(blocks.keys())
    result = []
    for key in sorted_keys:
        block_start, exposure, filt = key
        chunk_str = local_dt_to_chunk_str(block_start)
        if (chunk_str, exposure, filt) not in covered:
            result.append(blocks[key])
    return result


@multiple_ips
def find_unstacked_blocks(target, block_minutes=15):
    """Find time blocks of raw frames that have not yet been batch-stacked.

    Scans the raw light frames for *target*, groups them into clock-aligned
    time blocks of *block_minutes* duration, and returns blocks that don't
    yet have a matching ``CrowdSky_*`` output file.  Blocks are sub-grouped
    by (exposure, filter) so that mixed-mode observations produce separate
    stacks with compatible frames.

    Parameters
    ----------
    target : str
        Target name as it appears in folder names, e.g. ``"M 81"``.
    block_minutes : int
        Block duration in minutes.  Default 15.  Blocks are aligned to
        clock boundaries (e.g. ``:00``, ``:15``, ``:30``, ``:45``).

    Returns
    -------
    list[dict]
        Sorted list of unstacked sub-blocks.  Each dict contains:

        - ``block_start`` (datetime): Start of the time block.
        - ``block_end`` (datetime): End of the time block.
        - ``exposure`` (str): e.g. ``"20.0s"``.
        - ``filter`` (str): e.g. ``"LP"``.
        - ``files`` (list[str]): Sorted raw filenames in this sub-block.
        - ``frame_count`` (int): Number of files.

    Examples
    --------
    ::

        >>> from seestarpy import crowdsky
        >>> blocks = crowdsky.find_unstacked_blocks("M 81")
        >>> for b in blocks:
        ...     print(f"{b['block_start']:%H:%M}  {b['frame_count']} frames")

    """
    raw_files = data.list_folder_contents(f"{target}_sub")
    parsed = []
    for fname in raw_files:
        info = parse_light_filename(fname)
        if info:
            info["filename"] = fname
            parsed.append(info)

    if not parsed:
        return []

    blocks = group_frames_into_blocks(parsed, block_minutes)

    # Skip the current (incomplete) block
    now = datetime.now()
    blocks = {k: v for k, v in blocks.items() if v["block_end"] <= now}
    if not blocks:
        return []

    # Coverage from local CrowdSky_* files on the Seestar
    try:
        stacked_files = data.list_folder_contents(target)
    except Exception:
        stacked_files = {}
    covered = parse_coverage_from_filenames(stacked_files)

    return filter_covered_blocks(blocks, covered)


@multiple_ips
def stack_blocks(target, block_minutes=15, min_exptime=240, dry_run=False):
    """Find and batch-stack all unstacked time blocks for a target.

    This is the main CrowdSky orchestrator.  It discovers unstacked
    blocks via :func:`find_unstacked_blocks`, filters by minimum exposure
    time, and submits sequential batch stack jobs to the Seestar.

    After each successful stack the output file is renamed from the
    firmware's ``DSO_Stacked_*`` format to ``CrowdSky_*`` with the block
    boundary timestamp and filter encoded in the filename.  This makes
    re-runs fully idempotent.

    Parameters
    ----------
    target : str
        Target name, e.g. ``"M 81"``.
    block_minutes : int
        Block duration in minutes.  Default 15.
    min_exptime : float
        Minimum total effective exposure (``frame_count * exposure_seconds``)
        in seconds for a block to be worth stacking.  Default 240.
    dry_run : bool
        If ``True``, print what would be stacked without actually doing it.

    Returns
    -------
    dict
        Summary with keys: ``target``, ``blocks_stacked``, ``blocks_failed``,
        ``blocks_skipped``, ``results``.

    Examples
    --------
    ::

        >>> from seestarpy import crowdsky
        >>> result = crowdsky.stack_blocks("M 81", dry_run=True)
        >>> result = crowdsky.stack_blocks("M 81")

    """
    all_blocks = find_unstacked_blocks(target, block_minutes)

    summary = {
        "target": target,
        "blocks_stacked": 0,
        "blocks_failed": 0,
        "blocks_skipped": 0,
        "results": [],
    }

    # Filter by min_exptime
    eligible = []
    for block in all_blocks:
        exposure_seconds = float(block["exposure"].rstrip("s"))
        total_exptime = block["frame_count"] * exposure_seconds
        if total_exptime < min_exptime:
            summary["blocks_skipped"] += 1
            continue
        eligible.append(block)

    if not eligible:
        if dry_run:
            print(
                f"No eligible blocks for {target} "
                f"({len(all_blocks)} found, all below "
                f"min_exptime={min_exptime}s)"
            )
        return summary

    if dry_run:
        print(f"Dry run: {len(eligible)} blocks to stack for {target}")
        for block in eligible:
            start = block["block_start"].strftime("%H:%M")
            end = block["block_end"].strftime("%H:%M")
            exp_sec = float(block["exposure"].rstrip("s"))
            total = block["frame_count"] * exp_sec
            print(
                f"  {start}-{end}  {block['frame_count']} frames x "
                f"{block['exposure']} ({block['filter']}) = {total:.0f}s"
            )
        summary["results"] = eligible
        return summary

    # Stack each block sequentially
    for block in eligible:
        start = block["block_start"].strftime("%H:%M")
        end = block["block_end"].strftime("%H:%M")
        print(
            f"Stacking block {start}-{end} "
            f"({block['frame_count']} frames, "
            f"{block['exposure']} {block['filter']})..."
        )

        set_batch_stack_setting(f"MyWorks/{target}_sub", block["files"])
        start_batch_stack()

        # Poll until terminal state
        while True:
            time.sleep(3)
            status = get_batch_stack_status()
            if status is None:
                continue
            state = status.get("state", "")
            if state == "complete":
                stacked = status.get("stacked_img", "?")
                print(f"  Complete: {stacked} frames stacked")

                # Rename DSO_Stacked output -> CrowdSky with block info
                out_name = _rename_output(
                    target, block, status,
                )
                if out_name:
                    print(f"  Renamed -> {out_name}")

                clear_batch_stack()
                summary["blocks_stacked"] += 1
                summary["results"].append({
                    "block_start": block["block_start"],
                    "block_end": block["block_end"],
                    "exposure": block["exposure"],
                    "filter": block["filter"],
                    "status": "complete",
                    "frames": status.get("stacked_img"),
                    "output_file": out_name,
                })
                break
            elif state in ("fail", "cancel"):
                print(f"  {state.title()}: block {start}-{end}")
                clear_batch_stack()
                summary["blocks_failed"] += 1
                summary["results"].append({
                    "block_start": block["block_start"],
                    "block_end": block["block_end"],
                    "exposure": block["exposure"],
                    "filter": block["filter"],
                    "status": state,
                })
                break

    return summary


@multiple_ips
def list_targets():
    """List observation targets that have raw sub-frames available for stacking.

    Scans the Seestar's ``MyWorks`` folder for target/target_sub folder
    pairs, indicating targets with both stacked outputs and raw sub-frames.

    Returns
    -------
    list[dict]
        Each dict contains:

        - ``target`` (str): Target name.
        - ``raw_files`` (int): Number of files in the ``_sub`` folder.
        - ``stacked_files`` (int): Number of files in the main folder.

    Examples
    --------
    ::

        >>> from seestarpy import crowdsky
        >>> crowdsky.list_targets()
        [{'target': 'M 81', 'raw_files': 1052, 'stacked_files': 1}]

    """
    folders = data.list_folders()
    targets = []

    for name, count in folders.items():
        if name.endswith("_sub"):
            target = name[:-4]
            if target in folders:
                targets.append({
                    "target": target,
                    "raw_files": count,
                    "stacked_files": folders[target],
                })

    targets.sort(key=lambda t: t["target"])
    return targets


@multiple_ips
def stack_all(block_minutes=15, min_exptime=240, dry_run=False):
    """Find and batch-stack all unstacked time blocks for every target.

    Discovers targets via :func:`list_targets`, then calls
    :func:`stack_blocks` for each one sequentially.  If one target fails,
    the error is recorded and processing continues with the next target.

    Parameters
    ----------
    block_minutes : int
        Block duration in minutes.  Default 15.
    min_exptime : float
        Minimum total effective exposure in seconds.  Default 240.
    dry_run : bool
        If ``True``, preview what would be stacked without doing it.

    Returns
    -------
    dict
        Summary with keys: ``targets_processed``, ``targets_with_work``,
        ``total_blocks_stacked``, ``total_blocks_failed``,
        ``total_blocks_skipped``, ``per_target``.

    Examples
    --------
    ::

        >>> from seestarpy import crowdsky
        >>> crowdsky.stack_all(dry_run=True)
        >>> result = crowdsky.stack_all()

    """
    targets = list_targets()

    summary = {
        "targets_processed": 0,
        "targets_with_work": 0,
        "total_blocks_stacked": 0,
        "total_blocks_failed": 0,
        "total_blocks_skipped": 0,
        "per_target": [],
    }

    if not targets:
        print("No targets found.")
        return summary

    for i, t in enumerate(targets, 1):
        name = t["target"]
        print(f"[{i}/{len(targets)}] {name}")

        try:
            result = stack_blocks(
                name,
                block_minutes=block_minutes,
                min_exptime=min_exptime,
                dry_run=dry_run,
            )
        except Exception as exc:
            print(f"  Error: {exc}")
            result = {
                "target": name,
                "blocks_stacked": 0,
                "blocks_failed": 0,
                "blocks_skipped": 0,
                "results": [],
                "error": str(exc),
            }

        summary["targets_processed"] += 1
        had_work = (
            result["blocks_stacked"]
            + result["blocks_failed"]
            + result["blocks_skipped"]
        ) > 0
        if had_work:
            summary["targets_with_work"] += 1
        summary["total_blocks_stacked"] += result["blocks_stacked"]
        summary["total_blocks_failed"] += result["blocks_failed"]
        summary["total_blocks_skipped"] += result["blocks_skipped"]
        summary["per_target"].append(result)

    stacked = summary["total_blocks_stacked"]
    failed = summary["total_blocks_failed"]
    skipped = summary["total_blocks_skipped"]
    print(
        f"Done: {stacked} stacked, {failed} failed, {skipped} skipped "
        f"across {summary['targets_processed']} targets."
    )

    return summary


@multiple_ips
def purge_crowdsky_stacks(folder=None):
    """Delete all ``CrowdSky_*`` files from observation folders on the Seestar.

    Parameters
    ----------
    folder : str or None
        - A specific folder name (e.g. ``"M 81"``) — purge only that folder.
        - ``"all"`` or ``None`` — scan every non-``_sub`` folder and purge all.

    Returns
    -------
    dict
        ``{"folders_scanned": int, "files_deleted": int, "deleted": [str]}``
    """
    if folder is None or folder == "all":
        folders_to_scan = [
            name for name in data.list_folders()
            if not name.endswith("_sub")
        ]
    else:
        folders_to_scan = [folder]

    summary = {"folders_scanned": 0, "files_deleted": 0, "deleted": []}
    to_delete = []

    for target_folder in folders_to_scan:
        summary["folders_scanned"] += 1
        try:
            files = data.list_folder_contents(target_folder)
        except Exception:
            continue
        for fname in files:
            if fname.startswith("CrowdSky_"):
                to_delete.append((target_folder, fname))

    if not to_delete:
        print("No CrowdSky files found.")
        return summary

    conn = data._connect_smb()
    try:
        for target_folder, fname in to_delete:
            remote_path = f"{data.ROOT_DIR}/{target_folder}/{fname}"
            try:
                conn.deleteFiles(data.SHARE_NAME, remote_path)
                summary["files_deleted"] += 1
                summary["deleted"].append(remote_path)
                print(f"  Deleted: {remote_path}")
            except Exception as exc:
                print(f"  Failed to delete {remote_path}: {exc}")
    finally:
        conn.close()

    print(
        f"Purged {summary['files_deleted']} CrowdSky files "
        f"from {summary['folders_scanned']} folder(s)."
    )
    return summary
