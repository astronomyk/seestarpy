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

    # 2. Preview unstacked blocks
    crowdsky.stack_blocks("M 81", dry_run=True)

    # 3. Stack them
    crowdsky.stack_blocks("M 81")
"""

import re
import time
from datetime import datetime, timedelta

from . import data
from .connection import multiple_ips
from .stack import (
    clear_batch_stack,
    get_batch_stack_status,
    set_batch_stack_setting,
    start_batch_stack,
)

_LIGHT_RE = re.compile(
    r"^Light_(.+)_(\d+\.\d+s)_([A-Za-z]+)_(\d{8}-\d{6})\.fit$"
)
_DSO_STACKED_RE = re.compile(
    r"^DSO_Stacked_(\d+)_(.+)_(\d+\.\d+s)_(\d{8})_(\d{6})\.fit$"
)
# CrowdSky output files encode the block boundary timestamp and filter
# for deterministic coverage detection:
#   CrowdSky_<N>_<target>_<exposure>_<filter>_<YYYYMMDD>-<HHMMSS>.fit
_CROWDSKY_RE = re.compile(
    r"^CrowdSky_(\d+)_(.+)_(\d+\.\d+s)_([A-Za-z]+)_(\d{8}-\d{6})\.fit$"
)


def _parse_light_filename(filename):
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

        >>> _parse_light_filename("Light_M 81_20.0s_LP_20260227-225203.fit")
        {'target': 'M 81', 'exposure': '20.0s', 'filter': 'LP',
         'datetime': datetime(2026, 2, 27, 22, 52, 3)}

    """
    m = _LIGHT_RE.match(filename)
    if not m:
        return None
    return {
        "target": m.group(1),
        "exposure": m.group(2),
        "filter": m.group(3),
        "datetime": datetime.strptime(m.group(4), "%Y%m%d-%H%M%S"),
    }


def _floor_to_block(dt, block_minutes):
    """Floor a datetime to the nearest block boundary."""
    return dt.replace(
        minute=(dt.minute // block_minutes) * block_minutes,
        second=0,
        microsecond=0,
    )


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

    block_ts = block["block_start"].strftime("%Y%m%d-%H%M%S")
    new_stem = (
        f"CrowdSky_{frame_count}_{target}_{block['exposure']}"
        f"_{block['filter']}_{block_ts}"
    )
    old_stem = old_fit.removesuffix(".fit")

    folder = f"MyWorks/{target}"
    try:
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
    # 1. Get raw files and parse light frames
    raw_files = data.list_folder_contents(f"{target}_sub")
    parsed = []
    for fname in raw_files:
        info = _parse_light_filename(fname)
        if info:
            info["filename"] = fname
            parsed.append(info)

    if not parsed:
        return []

    # 2. Group into clock-aligned blocks by (block_start, exposure, filter)
    block_delta = timedelta(minutes=block_minutes)
    blocks = {}
    for p in parsed:
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

    # 3. Skip the current (incomplete) block
    now = datetime.now()
    blocks = {k: v for k, v in blocks.items() if v["block_end"] <= now}

    if not blocks:
        return []

    # 4. Determine which blocks are already covered.
    #
    # CrowdSky output files encode the block-start timestamp and filter
    # directly in the filename, so coverage is an exact match on
    # (block_start, exposure, filter).  We ignore plain DSO_Stacked files
    # for coverage since their timestamps reflect stacking time, not
    # observation time, making block mapping unreliable.
    try:
        stacked_files = data.list_folder_contents(target)
    except Exception:
        stacked_files = {}

    covered = set()
    for fname in stacked_files:
        m = _CROWDSKY_RE.match(fname)
        if not m:
            continue
        exposure_str = m.group(3)
        filt = m.group(4)
        dt = datetime.strptime(m.group(5), "%Y%m%d-%H%M%S")
        covered.add((dt, exposure_str, filt))

    # 5. Filter out covered blocks
    sorted_keys = sorted(blocks.keys())
    result = []
    for key in sorted_keys:
        if key not in covered:
            result.append(blocks[key])

    return result


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
