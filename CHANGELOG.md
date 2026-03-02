# Changelog

## v0.2.0 — 2026-03-02

### New modules

- **`stream.py`** — Live image streaming from the Seestar's binary socket
  protocol (ports 4800/4804). Supports one-shot grabs (`get_live_image`),
  continuous streaming with callbacks (`start_stream`), and a live
  matplotlib display window. Handles both ZIP-compressed stacked frames
  and raw Bayer preview frames. Includes auto-stretch for faint
  nebulosity and FITS/PNG/JPEG export.

- **`plan.py`** — Observation plan commands reverse-engineered from the
  official Seestar app v3.0.2. Send plans (`set_view_plan`), stop them
  (`stop_view_plan`), and query status (`get_running_plan`). All payloads
  confirmed via live traffic capture.

- **`stack.py`** — Batch stacking commands (`set_batch_stack_setting`,
  `start_batch_stack`, `stop_batch_stack`, polling via `iscope_get_app_state`).

- **`crowdsky.py`** — CrowdSky time-block stacking with WebDAV upload
  support.

### New features

- **`create_mosaic_plan()`** — Generate multi-panel observation plans that
  tile a rectangular sky region. Boustrophedon (snake) traversal minimises
  slew distance. Handles cos(dec) correction for RA spacing.

- **`plot_mosaic_plan()`** — Visualise mosaic panel layouts on a zoomed
  Mollweide projection with RA/Dec grid lines. Auto-zooms to 150% of the
  panel footprint area.

- **`set_default_ip(n)`** — Quick helper to switch `DEFAULT_IP` between
  multiple Seestars by number (e.g. `set_default_ip(2)` for
  `seestar-2.local`).

- **`@multiple_ips` decorator** — Moved to `connection.py` and applied to
  `ui`, `status`, `stack`, `crowdsky`, and `data` modules. Pass `ips=` to
  broadcast commands to multiple Seestars in parallel.

- **`data.py` refactored** — Now uses `get_albums` under the hood.
  Added filetype filter to `list_folder_contents` and graceful handling of
  missing folders. Multi-IP support via `@multiple_ips`.

- **`build_rtsp_url()`** — Helper to construct RTSP URLs for the Seestar's
  live H.264 video feeds (ports 4554/4555).

### Bug fixes

- **Stream display flicker** — The matplotlib live display now stays on
  the stacked frame once received, instead of alternating between
  stacked and preview frames on each heartbeat cycle.

- **Event listener shutdown** — Graceful shutdown replacing the
  `AttributeError` crash workaround.

- **`raw.set_settings`** — Updated to work with firmware v6.7.

### Documentation

- All docstrings updated to NumPy-style Sphinx/RTD format across the
  entire package.
- New Sphinx API pages for `plan`, `stack`, and `stream` modules.
- New tutorials: observation plans, live streaming.
- Protocol reference: image stream binary format documented in
  `docs/info/image_stream_protocol.rst`.

### Housekeeping

- Removed unused `stacking`, `old_code`, and `rtsp_client` modules.
- Moved `mobile_app` to separate `seestarpy-utils` repository.
- Removed `build` and `twine` from runtime dependencies (they were
  incorrectly listed as dependencies instead of dev tools).
- Added `click` to dependencies (required by CLI entry point).
- Added integration test framework (94 tests against live Seestar).
- Added `CLAUDE.md` for AI assistant onboarding.
