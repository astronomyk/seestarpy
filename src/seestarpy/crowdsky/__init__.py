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
