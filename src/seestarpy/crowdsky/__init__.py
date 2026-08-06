"""CrowdSky time-block stacking and server sync."""

from . import chunks, server

# Re-export public functions from chunks (backward compat)
from .chunks import (
    find_unstacked_blocks,
    stack_blocks,
    stack_all,
    list_targets,
    purge_crowdsky_stacks,
)

# Re-export core functions (pure logic, no Seestar I/O)
from .chunks import (
    parse_light_filename,
    group_frames_into_blocks,
    parse_coverage_from_filenames,
    filter_covered_blocks,
    local_dt_to_chunk_str,
    compute_chunk_key,
    LIGHT_RE,
    CROWDSKY_RE,
    CROWDSKY_RE_LEGACY,
)

# Re-export public functions from server
from .server import (
    set_credentials,
    set_base_url,
    list_stacks,
    upload_stack,
    upload_all_stacks,
    download_stack,
)


def sync(username=None, password=None, dest=".", block_minutes=15,
         min_exptime=240, skip_existing=True, dry_run=False,
         max_wait_sec=3600):
    """Stack all available frames, then upload the results to CrowdSky.

    One-call convenience pipeline: batch-stacks every unstacked time block
    for every target on the Seestar (:func:`stack_all`), then uploads all
    ``CrowdSky_*.fit`` stacks that the server doesn't already have
    (:func:`~seestarpy.crowdsky.server.upload_all_stacks`).

    Credentials are checked against the server *before* stacking starts,
    so a typo fails in seconds rather than after an hour of stacking.

    .. warning:: The two phases run strictly sequentially on purpose.  The
       Seestar's file-listing API keeps a single "current directory" cursor
       per device, so stacking and uploading must never list folders on the
       same scope concurrently — doing so silently skips blocks.  For the
       same reason, don't run ``sync()`` twice at the same time against
       one scope.

    Parameters
    ----------
    username, password : str, optional
        CrowdSky account credentials.  If omitted, previously configured
        credentials are used (:func:`~seestarpy.crowdsky.server.set_credentials`
        or the ``CROWDSKY_USERNAME`` / ``CROWDSKY_PASSWORD`` environment
        variables).
    dest : str or Path
        Local directory where stacks downloaded from the Seestar are saved
        before upload (kept afterwards).  Default ``"."``.
    block_minutes : int
        Time-block duration in minutes for stacking.  Default 15.
    min_exptime : float
        Minimum total effective exposure in seconds for a block to be
        stacked.  Default 240.
    skip_existing : bool
        If ``True`` (default), skip uploads whose chunk key already exists
        on the server.
    dry_run : bool
        If ``True``, preview both phases without stacking or uploading.
    max_wait_sec : float
        Maximum seconds to wait for the firmware to finish each block.
        Default 3600.

    Returns
    -------
    dict
        ``{"stack": <stack_all summary>, "upload": <upload_all_stacks
        summary>}``.

    Examples
    --------
    ::

        >>> from seestarpy import crowdsky
        >>> result = crowdsky.sync(username="alice", password="s3cret")

        >>> # Preview what would happen, using env-var credentials
        >>> crowdsky.sync(dry_run=True)

    """
    if (username is None) != (password is None):
        raise ValueError("Provide both username and password, or neither.")
    if username is not None:
        server.set_credentials(username, password)

    # Fail fast on bad/missing credentials before the (long) stacking phase.
    server.list_stacks()

    print("=== CrowdSky sync: stacking ===")
    stack_summary = chunks.stack_all(
        block_minutes=block_minutes,
        min_exptime=min_exptime,
        dry_run=dry_run,
        max_wait_sec=max_wait_sec,
    )

    print("=== CrowdSky sync: uploading ===")
    upload_summary = server.upload_all_stacks(
        dest=dest,
        skip_existing=skip_existing,
        dry_run=dry_run,
    )

    return {"stack": stack_summary, "upload": upload_summary}
