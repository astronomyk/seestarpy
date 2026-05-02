# Changelog

## v0.4.0 — 2026-05-02

### New features

- **`stream.show_current_stack()`** — Low-friction one-shot matplotlib
  viewer. Grabs the latest stacked frame and pops up an auto-stretched
  window in a single line:

  ```python
  from seestarpy import stream
  stream.show_current_stack()
  ```

  With `ips="all"` (or `ips=[1, 2]`) frames are fetched in parallel
  from all selected Seestars and tiled into a subplot grid on a single
  figure. Returns `(header, arr8)` for one scope or
  `{ip: (header, arr8)}` for many.

- **`connection.resolve_ips()`** — IP-resolution logic factored out of
  the `@multiple_ips` decorator into a public helper, so other code
  paths (like `show_current_stack`) can share the same `ips=`
  semantics without going through the decorator.

### Packaging

- **`cryptography` is now a standard dependency.** Firmware 7.18+
  authentication is the common case rather than the exception, so the
  separate `seestarpy[auth]` install variant has been removed. A plain
  `pip install seestarpy` now ships everything you need to authenticate
  against modern firmware. The openssl CLI fallback in `auth` stays as
  a runtime safety net.

### Behaviour changes

- **`stream.get_live_image()`** — Default `read_timeout` raised from
  8.0 s to 30.0 s to comfortably cover the 8MP S30 Pro frames over
  Wi-Fi.

## v0.3.1 — 2026-04-27

### Bug fixes

- **`stream.get_live_image()`** — skip past zero-dimension ack/keepalive
  frames the Seestar sends in response to image requests. Previously a
  one-shot grab would frequently return an empty header, causing
  `decode_payload` / `save_image` to raise
  `ValueError: Zero-dimension frame (ack/keepalive)` even when the
  scope was actively stacking. The function now loops on the socket up
  to `max_ack_frames` (default 10) until a frame with real dimensions
  arrives.

### New parameters on `get_live_image()`

- `max_ack_frames` (default 10) — bound the ack-skipping loop.
- `fallback` (default True) — if `get_stacked_img` yields no real
  frames (e.g. the scope just woke and stacking hasn't started), retry
  once on the same socket with `get_current_img` so callers always get
  *something* renderable when available.
- `read_timeout` (default 8.0 s) — bound per-recv waits so a silent
  Seestar can't strand a caller indefinitely.

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
