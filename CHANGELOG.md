# Changelog

## Unreleased

### New — blocking wrappers with live progress for the long operations

`polar_align`'s pattern is now shared by every firmware operation that takes
tens of seconds: issue the command inside a `connection.keepalive`, print a
progress line per event, and block until the firmware reports a terminal
state. The common machinery lives in `ui._await_operation`, which
`polar_align` was refactored onto.

- **`ui.autofocus(verbose=True, timeout=180)`** — new. Runs the focuser
  V-curve sweep, printing each position and its measured FWHM, and returns
  `{'state', 'position', 'lapse_ms', 'error', 'code'}`. `position` is read
  back after the sweep, since the `AutoFocus` event never reports where it
  settled. **A view must already be running**: the routine focuses on
  whatever the camera is exposing, so with the camera idle it fails with
  `'no star is detected'` (code 279).
- **`ui.goto` and `ui.goto_target`** now **block** until the mount reports
  the move finished, instead of returning as soon as the command is
  accepted, and print progress. Both gained `verbose` and `timeout`
  arguments. `goto` waits on the terminal event for the branch it took —
  `ScopeGoto`, `ScopeHome` or `ScopeMoveToHorizon` — so a park is not ended
  early by an unrelated slew. `goto_target` waits on `AutoGoto` and returns
  the resolved `target_name`/`ra`/`dec` alongside the outcome.

This is a **behaviour change** for existing `goto`/`goto_target` callers who
relied on them returning immediately. Pass `timeout=0` for the old
fire-and-forget semantics.

Two details the firmware forces on any such wrapper, both derived from the
152-event capture in `tests/event_output_20250722.dat`:

- A finished operation is reported **twice** — once as an inner frame
  (carrying `page`, or nothing but an error) and once as the operation's own
  frame carrying `lapse_ms` and/or `route`. Only the latter means the whole
  operation is over, so `ui._is_outer` distinguishes them; the inner frame is
  kept only as a fallback if no outer one ever arrives. Without this a
  retrying `AutoGoto` looks finished on its first failed attempt.
- A retrying `AutoGoto` re-emits `ScopeGoto working` several times per
  attempt, so consecutive identical progress lines are collapsed with an
  `(xN)` counter rather than burying the useful output.

Verified live on an S30 Pro (fw 8.89): `goto_target("NGC 3310")` resolved,
slewed and plate-solved in 30.4 s; `goto` completed verbose and quiet; the
`timeout` path returned cleanly at 300 s when cloud ended the session
mid-slew; and `autofocus` correctly reported code 279 on a field too low to
show stars. The autofocus *success* path is covered by unit tests only —
clouds closed in before it could be exercised on a rich field.

### Fixed — polar alignment was always cancelled ~19 s in

`raw.start_polar_align` could never complete a three-point alignment. The
firmware ties a 3PPA run to the TCP connection that issued the command, and
closes an idle port-4700 socket after **~15.5 s** (measured on fw 8.89).
`send_command` never pinged the pooled socket, so the firmware dropped it
mid-alignment, cancelled the run and left the mount stopped wherever it had
got to. Confirmed against a packet capture of the phone app, which holds one
socket open with `test_connection` heartbeats for the whole run — and matches
the app's own UI behaviour, where leaving the 3PPA screen aborts the
alignment and stops the scope on the spot.

The two symptoms this produced were the same abort seen from different
starting positions, not two bugs:

- **from EQ park** — the firmware's own slew to the first point takes ~45 s,
  so the abort landed mid-slew after ~85 deg of the ~137 deg of DEC travel.
  This looked like a mount limit ("only rotates 90 deg instead of 270"). It
  is not: a plain `scope_goto` covers the same ground to the zenith fine.
- **from a deployed position** — the slew is short, so the run got through
  the first plate-solve and `move1` before dying in `delay1`. This looked
  like "bugs out after a single movement".

Added:

- **`connection.keepalive`** — a context manager that pings a scope's command
  connection every `connection.KEEPALIVE_INTERVAL` (5 s) so the firmware
  won't drop it, for any operation the firmware binds to its connection.
  Reference-counted, so nested use is safe. Unsolicited events read off the
  socket are forwarded to an optional `on_event` callback, which makes the
  keepalive ping double as an event pump — no second socket or listener
  thread is needed to follow progress.
- **`ui.polar_align(dec_pos_index=3, restart=True, verbose=True,
  timeout=300)`** — holds the connection open, blocks until the firmware
  reports a terminal state, prints per-event progress by default, and returns
  `{'state', 'total', 'x', 'y', 'lapse_ms'}`. `state` is `complete`, `fail`,
  `cancel` or `timeout`; `total` is the polar-axis error in degrees, `x` its
  azimuth and `y` its altitude component.

Verified live on an S30 Pro (fw 8.89) at `dec_pos_index` 2, 3 and 4: three
independent alignments spanning dec 18 to 78 deg agreed to ~1 arcmin
(1.0696, 1.0721, 1.0882 deg), and matched the phone app's own measurement
that night to 0.0002 deg in azimuth.

Also corrected two wrong claims in the `raw.start_polar_align` docstring: the
mount has no ~270 deg travel limitation, and `restart=False` is a
*re-measure* at the current position (`3PPA` `calc4`, `state_code` 17) for
checking the residual after adjusting the tripod — not a "continue to the
next point". Documented the `state_code` ladder, and that the DEC band is
`dec = latitude + 30 * (dec_pos_index - 3)`.

### Removed — one dependency, two modules, and the last duplicate paths

Second pass of the audit, acting on the judgement calls the first pass
deliberately left open.

- **`websockets` is no longer a dependency.** `event_listener` no longer
  starts a WebSocket relay on `ws://0.0.0.0:8765`, and `start_listener` has
  lost its `with_websocket` parameter. The relay's only consumers were the
  single-scope `basic.html` / `fancy.html` pages removed in 0.7.0;
  `seestarpy.dashboard` serves its own page over HTTP with its own per-scope
  connections. Read `event_stream.LATEST_STATE` to feed a UI of your own.
- **`events.event_definitions` deleted** (878 lines, ~40 dataclasses). It had
  no runtime consumer: the live path stores raw dicts in `LATEST_STATE` and
  the dashboard reads raw dicts. Recoverable from git history if a typed
  event layer is ever wanted. `tests/test_event_definitions.py` went with it.
- **`auth._sign_with_openssl` deleted.** `cryptography` stays a mandatory
  dependency, so the shell-out fallback was unreachable; `sign_challenge` is
  now one path that raises a clear `ImportError` on a broken install.
  `subprocess` and `tempfile` are no longer imported.
- **`plan.create_quadrilateral_plan` deleted** — a bare alias for
  `create_polygon_plan`, which is the same function under the name it
  outgrew.
- **`raw.get_stacked_img` deleted.** A port-4800 image-stream method that
  could only ever return `code 103` on the command socket; `stream.get_live_image()`
  is the working equivalent and already speaks the right protocol.

### Changed

- **`status.py` no longer builds its own JSON-RPC payloads.** `get_exposure`,
  `get_filter` and `get_target_name` now call `raw.get_setting`,
  `raw.get_wheel_position` and the new `raw.get_sequence_setting`. The two
  that hand-rolled payloads were the two that mishandled the reply envelope,
  which is exactly the thing `raw` already gets right. `send_command` is no
  longer imported here.
- **New `raw.get_sequence_setting`** — reads `group_name` and the
  end-of-sequence flags. The setter existed; the getter did not.
- **One numeric coercion for the package.** `status.as_number` (value or
  `None`) and `status.coord_pair` (a coordinate pair from either firmware's
  reply shape) are now the single implementations;
  `dashboard.monitor` imports them instead of keeping byte-identical copies,
  and `status._num` is a thin display wrapper over `as_number`.
- **One cached firmware accessor.** `status.firmware_version(ip=None,
  refresh=False)` returns `(version_string, version_int)`, cached per address
  — the seam that firmware gates (7.75 stacking paths, 8.46 preview block)
  can share. `status.get_firmware_version` and `stack._firmware_ver_int` both
  read through it, replacing a second cache in `stack.py`. A failed read is
  not cached, so a scope that was mid-boot gets retried.
- **`data.list_folders` documents that it is incomplete.** It reads the
  firmware's `get_albums`, which under-reports by 0–8 folders (measured across
  six scopes; worst case 33 albums for 41 real directories). The docstring now
  says so and shows the SMB listing to use when completeness matters. There is
  no folder cap — an apparent 100-folder limit was a misdiagnosis.
  `list_folder_contents` gained the two caveats that bite in practice: the
  per-device page cursor that must not be walked concurrently, and its
  kilobyte-rounded sizes. SMB and `pysmb` stay as the reliable path.
- **`raw.scope_get_ra_dec`'s docstring corrected.** It claimed firmware 8.x
  rejects the method with `code 103`; measured live on 8.46 and 8.89, both
  accept it (`code 0`). The real incompatibility is the return *shape* — a
  three-element `[ra, dec, lst]` list where `scope_get_equ_coord` gives a
  dict. The same wrong claim is fixed in the status-checks tutorial and in a
  `status_bar` comment.

### Removed — dead code

An audit of `src/` cross-referenced every top-level symbol against the whole
repo, then probed the questionable JSON-RPC methods live on firmware 8.46
(S50) and 8.89 (S30 Pro). Everything below either had no consumer anywhere,
or sent a wire method that **both** scopes answered with `code 103`
("method not found"). Nothing here could have worked on any firmware
seestarpy 0.7 supports.

- **`events.event_watcher`** — deleted. `EventWatcher` had no consumer and
  three independent fatal defects: it never authenticated, so it could not
  connect to firmware 7.18+ at all; `_handle_event` did
  `ev_class(**json.dumps(data))`, and `**` on a `str` raises `TypeError`;
  and it called an `update()` method that no `event_definitions` dataclass
  has. Use `start_listener`, or `seestarpy.dashboard` for several scopes.
- **`coordintate_utils`** — deleted. The whole module was unreachable:
  `get_mount_alt_az_from_latest_state` had no callers, and it was the only
  caller of `ra_dec_to_alt_az`. The mount reports Alt/Az directly via
  `scope_get_horiz_coord`, which `status.get_coords()` already uses.
- **`raw.scan_iscope`** — deleted. A real method sent on the wrong socket:
  it belongs to UDP discovery on port 4720, which `connection.discover()`
  speaks. On the command socket it could only ever return `103`.
- **`raw.stop_goto_target`, `raw.stop_scheduler`** — deleted; `103` on both
  scopes and absent from the v3.3.0 `CmdMethod` enum. To cancel a slew use
  `raw.iscope_stop_view("AutoGoto")`, which is what the official app sends.
- **`raw.set_stack_setting`** — deleted. Deprecated since v0.1.2 and removed
  from the firmware at v6.7, below the oldest firmware 0.7.x supports, so it
  could not change a setting on any supported scope. Use `raw.set_setting`.
  (`raw.get_stack_setting` is **kept**: unlike its setter it falls back to
  `get_setting` on `103`, so it still returns useful data.)
- **`status.get_target_name2`** — deleted. It called `get_img_name_field`,
  which returns filename-component toggles
  (`{"bin": true, "date_time": true, …}`) and contains no target name.
- **`data.HTTP_PORT`** — deleted; never read, and `_build_http_url` relies on
  the default port 80 instead.
- **Four commented-out stubs in `raw.py`** (`begin_streaming`,
  `stop_streaming`, `get_annotated_result`, `get_event_state`) and their
  `"""To implement:"""` heading — 61 lines. `begin_streaming` /
  `stop_streaming` are genuine port-4800 methods that `stream.py` already
  uses correctly. Note `get_annotated_result` was a typo: the real method is
  `get_annotate_result`, which is live and still unwrapped.
- **Six `_`-prefixed backward-compat aliases in `crowdsky.chunks`**
  (`_LIGHT_RE`, `_CROWDSKY_RE`, `_CROWDSKY_RE_LEGACY`,
  `_parse_light_filename`, `_local_dt_to_chunk_str`, `_compute_chunk_key`).
  The first three had no consumer at all; the rest were imported only by
  `tests/test_stack_blocks.py`, now repointed at the public names. The
  public `CROWDSKY_RE_LEGACY` is still used and stays.
- **`src/__init__.py`** — deleted. An empty top-level package file that made
  `import src.seestarpy` resolve, loading every module a second time under a
  second name. It is never installed (`packages = ["src/seestarpy"]`), and it
  is how `event_watcher`'s `from src.seestarpy.connection` import stayed
  hidden. `tests/test_event_definitions.py` now imports `seestarpy.events`.

### Fixed — defects the audit turned up

Four of these were documented as working. All are covered by new regression
tests in `tests/test_audit_fixes.py`.

- **`ui.filter_wheel("lp")` and `("ircut")` raised `ValueError`** — the two
  names the docs lead with. The guard tested `pos.lower() in ["open",
  "narrow"]` while the mapping beside it handled four keys, so half the
  supported names fell through to the error branch. Guard and mapping are now
  one dict, and the message lists what is accepted.
- **`ui.goto("m42")` returned `None` instead of raising** — for any string
  that was not `'park'` or `'horizon'`, both inner tests failed and the
  function fell off the end, leaving `else: raise ValueError` unreachable for
  every `str`. A typo'd target was a silent no-op that read as success.
- **`status.get_target_name()` always returned `None`** — it read
  `group_name` off the JSON-RPC envelope instead of out of `result`, where
  the firmware actually puts it.
- **`status.status_bar(return_type=...)` ignored its argument** — `"dict"`
  returned the formatted string, contradicting the docstring. The dict is now
  real: `status_bar` computes one dictionary of every cell and renders the
  table from it, so the two return types cannot disagree. Absent fields are
  `None` rather than the table's `"---"`, numbers are unrounded, and an
  unknown *return_type* raises instead of silently giving a string.
- **`connection.keepalive` silently did nothing useful when
  `PERSIST_CONNECTIONS` was False** — with pooling off the socket is closed
  after every command, so there is nothing to keep alive and the firmware
  would cancel a polar alignment ~15 s in, exactly as it did before keepalive
  existed. It now raises on entry with an explanation, rather than failing
  15 s into a run.
- **The mDNS path's `timeout` never applied** — in
  `find_available_ips(mdns=True)` the `ThreadPoolExecutor` context manager
  exited (joining every lookup) *before* `as_completed(..., timeout=…)` was
  reached, so the timeout could not fire and a subnet where
  `seestar-N.local` does not resolve blocked for the full DNS timeout per
  name. Collection now happens inside the pool's lifetime and shutdown does
  not wait, making *timeout* an actual bound.
- **`events.event_listener` held an import-time snapshot of `DEFAULT_IP`** —
  `from ..connection import DEFAULT_IP` binds a copy, so a listener started
  after `set_default_ip()` connected to the *previous* scope, silently. It
  now resolves `connection.current_ip()` per connection attempt, and reads
  `VERBOSE_LEVEL` live for the same reason.
- **`tests/integration/test_13_seq_error_recovery.py`** passed for the wrong
  reason: it cancelled a slew with `raw.stop_goto_target()`, which the
  firmware refuses, so the goto simply ran to completion and the assertion
  held anyway. Now uses `raw.iscope_stop_view("AutoGoto")`.

## v0.7.0 — 2026-08-18

> **One screen for the whole fleet.** A new web dashboard replaces the old
> single-scope HTML pages: it discovers every Seestar on the network by
> itself, gives each one a card with its live stacked image and status, and
> adds or drops cards as scopes come and go.

### New: `seestarpy.dashboard`

- **`python -m seestarpy.dashboard`** (or `dashboard.serve()`) starts an
  HTTP server that finds every Seestar via UDP discovery, holds an event
  connection and an image stream open to each, and serves one card per
  scope. Cards show the current **stacked** image, falling back to the live
  preview when the scope isn't stacking, with exposure/stack/dropped/filter,
  target/RA-Dec/Alt-Az/view-state, and mount/battery/temperature/free-space
  down the side.
- Scopes powered on later appear on their own — discovery re-runs every 60 s
  (`--rescan`), and a scope that moved address is re-pointed at it. Cards are
  ordered by serial number so a scope holds its place in the grid.
- The browser is fed by **Server-Sent Events** (`/api/events`, one fleet
  snapshot a second); images are served separately and versioned by frame
  sequence, so a card only re-fetches a JPEG when there is a new one.
- Bind defaults to `0.0.0.0`, so the dashboard is readable from a phone or
  tablet elsewhere on the network.
- Needs NumPy and Pillow for image decoding: `pip install "seestarpy[dashboard]"`.
  Without them the status half of every card still works.
- **Removed** `seestarpy/dashboards/` (`basic.html`, `fancy.html` and their
  JS). Those pages rendered one scope from the `start_listener` WebSocket;
  the new dashboard runs its own per-scope connections and does not need
  `start_listener`. `events.event_listener.dashboard_url()` now returns the
  new dashboard's URL.

### Image stream: firmware 8.46 JPEG mode

Firmware 8.46 added a `preview` settings block that changes how stacked
frames cross the wire. Measured on an 8 MP S30 Pro over Wi-Fi:

| `image_transfer_mode` | `img_type` | frame size | time |
|---|---|---|---|
| `"Jpg"` | 4 | ~2.5 MB | ~5 s |
| `"Raw"` | 5 | ~49.8 MB | ~30 s |

- **`raw.set_image_transfer_mode`** — New. Selects `'Jpg'` or `'Raw'`
  (aliases `'jpeg'`, `'compressed'`, `'lossless'`, `'full'`), validated
  before the round-trip. Note this is a **persistent device setting** shared
  with the phone app, not a per-connection option.
- **`raw.get_preview_setting`** — New. Returns the `preview` block
  (`image_transfer_mode`, `rtsp_quality`, `rtsp_width`, `rtsp_height`), or
  `None` on firmware that predates it.
- **`stream.decode_payload`** now decodes JPEG payloads, returning **uint8**
  RGB (already stretched by the firmware) rather than linear uint16. New
  `stream.to_display8` centralises the "stretch unless it is already 8-bit"
  decision, so `save_image`, `show_current_stack` and the live matplotlib
  display all handle both.
- New helpers **`stream.is_image_frame`** and **`stream.is_stacked_frame`**,
  plus the `IMG_TYPE_ACK` / `IMG_TYPE_JPEG` constants.

### Fixed

- **The frame header is 80 bytes, not 34** — only its first 34 bytes carry
  named fields, and the true size is announced at offset 4. `_read_frame`
  skipped 34 and left the other 46 in the stream, so *every* payload came
  back 46 bytes early and 46 bytes short and the stream desynced after each
  frame (masked until now because the reader re-syncs on the magic number,
  and because a 46-byte shift in raw pixel data is invisible). This is also
  the real explanation for the old "the Seestar prepends a variable number
  of zero bytes before the ZIP header" comment. `parse_header` now returns
  `header_size` and `_read_frame` consumes it.
- **JPEG frames were discarded as acks** — they report `width`/`height` as
  `0` (the dimensions live inside the JPEG), and the "is this an image?"
  test was `width and height`. On firmware 8.46 the reader waited for a
  frame that had already arrived until the scope dropped the connection,
  which looked exactly like a scope refusing to stream.
- **`stream.decode_payload` on firmware 7.75+** — `get_stacked_img` returns
  16-bit RGB **uncompressed** on the S30 Pro, not ZIP-wrapped, and the
  decoder rejected it outright (`Unknown payload format: 49766400 bytes`).
  Both transports are now accepted. Payload sizes are also checked *before*
  scanning for the ZIP signature, which is both faster and safer — those
  four bytes occur by chance in roughly one uncompressed 50 MB frame in a
  hundred.
- **`import seestarpy` crashed on a cp1252 console** — discovery prints
  `✓`/`✗`/`→`, and since `find_seestar()` runs at import time the resulting
  `UnicodeEncodeError` took the whole package down on an unconfigured
  Windows terminal. Those lines now degrade to ASCII when the console
  cannot encode them.
- **`events.event_watcher` could not be imported at all** — it imported
  `from src.seestarpy.connection import ...`, which only resolves when the
  repository root happens to be on `sys.path`. Now a relative import, so
  the module (and its API page) works from an installed package.

### Docs

The tutorial pages were brought back in line with the code:

- *Connecting to your Seestar* rewritten around **UDP broadcast discovery**
  — the old page still described mDNS as the mechanism rather than the
  fallback. Now covers `discover()`, `DISCOVERED` / `AVAILABLE_IPS`, every
  shape the `ips=` keyword accepts, `set_default_ip`, and the persistent
  connection pool.
- *Live Image Streaming* covers the **80-byte header**, the firmware 8.46
  **JPEG transfer mode** (and why you must check the returned dtype),
  `to_display8`, `is_image_frame` / `is_stacked_frame`.
- *Observing* documents `ui.dither()`, which shipped undocumented, and
  fixes `set_user_location(long=…)` → `lon=`.
- *Managing files* documents `upload_files` / `upload_folder`, names the
  transport each operation uses, and warns about the two ways a bulk
  download bites: silent HTTP truncation on weak Wi-Fi, and the per-device
  listing cursor that must never be walked concurrently.
- *CrowdSky* documents `sync()` and corrects the HEALPix parameters in the
  filename convention (**NSIDE=128, RING** — was documented as 64, nested).
- *Changing settings* gained a section on the settings dictionary itself
  (nested blocks are replaced, not merged) and on `image_transfer_mode`.
- *Observation plans* gained the operational traps: backdating `start_min`
  to start or restart a plan immediately, app-triggered autofocus silently
  cancelling a running plan, `plan_target_af` / `viewplan_gohome`, and why
  Alt-Az mosaics must be planned around the inscribed circle.
- *Status checks* and *Setting the gain* expanded from stubs; status checks
  now also covers the event listener as an alternative to polling.
- `crowdsky.healpix` added to the API reference; the orphaned
  *Sniffing port 4700* page is now in the toctree.

### Packaging and testing

- **Versioning policy.** From this release the **minor** version tracks the
  oldest Seestar **major** firmware version still supported. `0.7.x` supports
  firmware 7.x (tested against 7.18 and 7.75) and everything newer, up to
  8.89 at the time of writing. When support for firmware 7 is dropped, this
  becomes `0.8`.
- **`pytest` no longer touches a telescope.** The suite used to run the live
  integration tests automatically whenever a Seestar answered on port 4700,
  which meant an innocent `pytest` on the observing laptop started driving
  the mount. Live tests are now strictly opt-in:

  | command | what runs |
  |---|---|
  | `pytest` | offline only — nothing reaches the network |
  | `pytest --live` | adds the live-hardware tests |
  | `pytest --live --no-movement` | live, minus anything that slews, parks, opens the arm or focuses |

  The new `movement` marker covers the 31 tests that physically move the
  scope, for when it is still in its box.
- **New `[stream]` extra.** `numpy` and `pillow` were only reachable through
  `[dashboard]`, but `stream.decode_payload` and `save_image` have always
  needed them — `pip install seestarpy` then saving a frame raised
  `ImportError`. The core package stays dependency-light; install
  `seestarpy[stream]` for pixels, `seestarpy[dashboard]` for the web UI
  (which now pulls `[stream]` in).
- **The dashboard binds loopback by default.** It has no authentication, so
  `0.0.0.0` is now opt-in via `serve(lan=True)` / `--lan` rather than the
  default.
- **CI** runs the offline suite on Python 3.11-3.13 and builds the docs with
  warnings-as-errors. It also imports every module from outside the repo
  root, which is the check that would have caught the `event_watcher` bug.
- `stream.auto_stretch` is now public (the STF described above), replacing
  the private `_auto_stretch`; the old name remains as an alias.
- `get_live_image` against a parked or idle scope raised
  `ConnectionError: Connection closed after 0/1 bytes`, which reads as a
  network fault. It now explains that the scope has no image to send.

## v0.6.0 — 2026-08-06

> **Getting data on and off the scope.** Three new capabilities: switch the
> USB-C port between mass-storage and wired-LAN roles, upload files *to* the
> Seestar over SMB (not just download), and run the whole CrowdSky
> stack-then-upload pipeline with one call. Includes the changes from
> v0.5.2, which was bumped but never published.

### USB-C port control

- **`raw.set_usb_mode`** — New. Switches the USB-C port between `'file'`
  (mass-storage gadget: the scope mounts as a drive) and `'net'` (USB host
  driving an external Ethernet adapter). Accepts the aliases `'drive'`,
  `'storage'`, `'usb'` and `'eth'`, `'ethernet'`, `'lan'`, and rejects
  anything else with a `ValueError` before the round-trip — the firmware
  answers `code 102` for any other spelling.
- **`raw.get_usb_mode`** — New. Reports `{'typec_mode', 'usb_en_eth'}`.
- Both modes write **both** settings. The firmware does not couple
  `typec_mode` and `usb_en_eth`, so writing the role alone leaves the
  master switch latched and a `'file'` switch would not undo a `'net'`
  switch. Verified live across four scopes on firmware v8.46.
- A scope in `'net'` mode is **dual-homed** — it keeps Wi-Fi and picks up a
  second wired DHCP lease, and both addresses answer on port 4700. The
  wired address appears nowhere in the API (`get_device_state`'s `station`
  block describes only Wi-Fi, and there is no `eth0` section), and mDNS
  tends to advertise the wired lease rather than the Wi-Fi one. See
  *Changing the Seestar's settings* in the docs.
- Wired mode needs a **powered** USB-C-to-Ethernet adapter with PD; the
  setting alone only arms the firmware.

### Uploading to the Seestar

- **`data.upload_files`** — New. Uploads specific local files into
  `MyWorks/<folder>` on the scope's eMMC over SMB, creating the folder if
  needed. Idempotent: unless `overwrite=True`, a file already present with
  a matching byte size is skipped, so a re-run after a dropped connection
  resumes instead of re-sending.
- **`data.upload_folder`** — New. Same, for a whole local directory with
  optional `fnmatch` pattern filtering.
- Together these make off-telescope sub-frames stackable on the scope:
  upload the subs, then point `stack.set_batch_stack_setting` at
  `MyWorks/<folder>`.

### CrowdSky

- **`crowdsky.sync`** — New one-call pipeline: batch-stack every unstacked
  time block for every target, then upload the resulting `CrowdSky_*.fit`
  stacks the server doesn't already have. Credentials are validated
  *before* stacking starts, so a typo fails in seconds rather than after an
  hour. The two phases run strictly sequentially by design — the Seestar's
  file-listing API keeps one directory cursor per device, so concurrent
  listing silently skips blocks.
- Stack upload timeout raised from 30 s to 60 s for the connect phase.

### Fixes

- **`raw.get_usb_mode` / `raw.set_usb_mode`** call `send_command` directly
  instead of nesting `@multiple_ips` wrappers. A nested call re-validates
  the inherited IP against `connection.AVAILABLE_IPS`, which only holds the
  address discovered at import time, so targeting any other scope died with
  `ValueError: max_workers must be greater than 0`. Other nested
  `@multiple_ips` pairs are still affected; `resolve_ips` rejecting a bare
  IP string it documents as valid is a separate open issue.
- `docs/conf.py` reported `v0.3.0` as the release for three versions.

### Docs

- New tutorial page: installing on a Raspberry Pi.
- *Changing the Seestar's settings* gained a USB-C section covering port
  roles, the PD-adapter requirement, and how to find a wired scope's
  address.

## v0.5.2 — 2026-07-20

> **Discovery:** network discovery now identifies *which* Seestar answered,
> not just where. Every discovery/print path shows a short
> ``model_serial`` device id (e.g. ``s50_a3497936``, ``s30pro_ce545589``),
> and the serial number is queryable directly. Verified live on an S50 and
> an S30 Pro (firmware v7.75).

### Device identification

- **`connection.find_available_ips`** — Each found Seestar is now queried
  (in parallel, with a short timeout) for its model and serial number:
  `✓ Found seestar.local at 192.168.1.81 (s50_a3497936)`. Hosts are listed
  in hostname order. A scope that resolves but can't be queried on port
  4700 still prints without the id — discovery never hangs on a wedged
  scope.
- **`connection.find_seestar`** — The import-time "Seestar found at" line
  includes the device id. (The module-level auto-discovery call moved to
  the end of `connection.py` to make this possible; no behaviour change.)
- **`connection.set_default_ip`** — Prints the device id alongside the
  hostname: `DEFAULT_IP → 192.168.1.78 (seestar-2.local, s30pro_ce545589)`.
- **`status.get_serial_number`** (alias **`status.get_sn`**) — New helper
  returning the bare serial number (e.g. `'a3497936'`). Accepts `ips=` for
  multi-Seestar queries.
- Device ids are cached per IP for the session (successful lookups only),
  so repeated calls don't re-query the scope.
- **`_Connection.send`** gained a `quiet=` flag so internal discovery
  queries don't spam the console at the default `VERBOSE_LEVEL`.

## v0.5.1 — 2026-07-09

> **Compatibility:** a bug-fix release that makes several calls
> **firmware-tolerant** across the v6.x–v8.x generations. Getters that were
> renamed or removed in newer firmware now fall back automatically, so the
> same code works on old and new Seestars. Verified live on firmware v7.75;
> diagnosed against firmware v8.46.

### Firmware v8.x compatibility

- **`status.status_bar` / `status.get_coords`** — Fixed a hard crash on
  firmware v8.x. They queried `scope_get_ra_dec`, a port-4800 heartbeat that
  the command socket rejects on newer firmware; the command-socket RA/Dec
  getter is `scope_get_equ_coord`. The error placeholder then reached
  `round("---")` and raised `TypeError`. Both functions now use
  `scope_get_equ_coord` and tolerate its two return shapes (newer firmware
  returns `{"ra": .., "dec": ..}`, older a `[ra, dec]` list). `status_bar`
  also degrades any missing/non-numeric cell to `---` instead of crashing.
- **`raw.scope_get_ra_dec`** — Now falls back to `scope_get_equ_coord` when
  the firmware answers `code 103` ("method not found").
- **`raw.get_stack_setting`** — The `get_stack_setting` RPC was removed from
  the firmware at v6.7. The (deprecated) wrapper now falls back to
  `get_setting` on `code 103` while still returning the native response on
  older firmware.
- **`raw.get_stacked_img`** — Deprecated. It is a port-4800 binary
  image-stream method (not a command-socket RPC) and is rejected on port
  4700 with `code 103`; use `stream.get_live_image()` to fetch the latest
  stacked image.
- **`raw.scope_move_to_horizon`** — Unchanged on the wire (still valid, no
  params). Docstring now notes that an apparent failure is usually a
  precondition: the scope must be awake/initialised before it honours the
  move.

### Batch stacking

- **`stack.set_batch_stack_setting`** — Now firmware-aware: detects
  `firmware_ver_int` per Seestar and sends full relative sub-frame paths on
  firmware ≥ 7.75 (int 2775) but bare filenames on older firmware (e.g.
  6.58, 7.32), which reject full paths with `state="fail"`, `error="no
  image"`, `code=267`. Fixes batch stacking (and
  `crowdsky.stack_blocks`/`stack_all`) on pre-7.75 scopes.

## v0.5.0 — 2026-06-16

> **Compatibility:** this release targets the **Seestar app v3.2.0 /
> firmware v7.75** generation. The onboard batch-stacking workflow
> (`stack`, `crowdsky`) now sends sub-frame paths in the form v7.75
> requires; on earlier firmware that path format is not guaranteed to work.
> **If your Seestar runs firmware earlier than v7.75 (app < v3.2.0), pin a
> previous seestarpy release** (e.g. `pip install "seestarpy<0.5"`).
> Firmware 7.18+ authentication (a signing key) is still required.

### Connection / session layer

- **`connection.multiple_ips`** — No longer mutates the shared module
  global ``DEFAULT_IP`` to retarget calls. Concurrent broadcasts to
  multiple Seestars previously raced on that global, so a command could be
  sent to the wrong scope. Each worker now sets a per-thread active IP
  (``connection.current_ip()``), and nested decorated calls inherit the
  outer scope instead of snapping back to ``DEFAULT_IP``.
- **`connection.send_command`** — Reuses one persistent, authenticated TCP
  connection per Seestar (``_Connection`` pool) instead of opening a fresh
  socket and re-running the firmware 7.18+ RSA handshake on every call. A
  long polling loop (e.g. `stack_blocks`) now authenticates once rather
  than once per poll. Drops are detected and the next call reconnects,
  re-authenticates and retries once; ``close_connections()`` (also run at
  interpreter exit) tears the pool down. Toggle with
  ``connection.PERSIST_CONNECTIONS``. Note: on an unrecoverable failure it
  now raises ``ConnectionError`` instead of returning an empty string.
- **`data._connect_smb` / `data._build_http_url` / `crowdsky._read_fits_ra_dec`**
  — Resolve the target host via ``connection.current_ip()`` so multi-IP
  broadcasts address the right Seestar.
- **`auth`** — Clearer ``AuthenticationError`` message: a rejected
  ``verify_client`` now means the signature didn't match this firmware
  (re-extract the key), not the previously-implied "code=None" case that
  the id-matching handshake fix already eliminated.

### Bug fixes — CrowdSky output rename

- **`crowdsky._rename_output`** — No longer fails silently. The
  idempotency-critical ``.fit`` rename is attempted first and treated as
  fatal on failure (returns ``None`` and warns that the block is *not*
  covered and will be re-stacked), while ``.jpg`` / ``_thn.jpg`` companions
  are now best-effort: a missing companion no longer aborts the whole
  rename and undoes a good ``.fit`` rename. SMB-connect failures and the
  ``HP000000`` HEALPix placeholder (from an unreadable RA/Dec header) now
  emit explicit warnings. `stack_blocks` records a ``rename_failed`` flag in
  each completed block's result.
- **`crowdsky._read_fits_ra_dec`** — Reads 8 FITS header blocks (23040 B)
  instead of 2, so RA/Dec parsing is robust to larger headers.

### Bug fixes — firmware v7.75 onboard stacking

- **`stack.set_batch_stack_setting`** — Firmware v7.75 no longer resolves
  bare sub-frame filenames; it requires each ``files`` entry's ``name`` to
  be a **full relative path from the SD-card root** (e.g.
  ``"MyWorks/NGC 7000_sub/Light_....fit"``). Bare names made the firmware
  fail instantly with ``state="fail"``, ``error="no image"``, ``code=267``.
  Bare filenames are now prefixed with ``path`` automatically; entries that
  already contain a ``/`` are sent unchanged, so callers don't have to
  change. The JSON-RPC method name and ``params`` shape are unchanged from
  v3.0.2 — only the file-name resolution changed. Confirmed live on a
  Seestar S30 Pro (firmware 7.75) on 2026-06-15.
- **`stack.clear_batch_stack`** — Now calls the firmware's direct
  ``clear_batch_stack`` JSON-RPC method (present and returning ``code=0``
  on v7.75), falling back to the legacy ``clear_app_state`` /
  ``{"name": "BatchStack"}`` approach if the firmware returns ``code=103``.
- **`auth` handshake** — The challenge/response reader now matches replies
  by JSON-RPC ``id`` and skips interleaved unsolicited events
  (``PiStatus``, ``temp``, …). Previously the first ``\r\n`` frame after a
  command was assumed to be its reply, so events streamed during an active
  batch stack were occasionally parsed as the ``verify_client`` reply,
  causing intermittent ``AuthenticationError (code=None)`` failures while
  polling stack progress.
- **`crowdsky.stack_blocks` / `stack_all`** — Hardened the per-block loop:
  clears stale ``BatchStack`` state before configuring, checks the
  ``start_batch_stack`` response code, surfaces the firmware error string
  on failure, handles unexpected states, and adds a ``max_wait_sec``
  (default 3600 s) timeout so a wedged block can no longer hang the run.

## v0.4.2 — 2026-05-04

### Bug fixes / behaviour

- **`crowdsky._request`** — Reverted the shared timeout default to a
  flat 30 s. The 0.4.1 change had pushed the long `(30, 300)` tuple
  into every call site, including small reads like `list_stacks()`
  and `raw_start_session()`, which would now hang for up to 5 minutes
  on a stuck server before failing.
- **`crowdsky.upload_stack`** — Now overrides the timeout locally with
  `(30, 300)`, so the long read window only applies to the actual
  ~12 MB FITS upload that needs it. Other crowdsky calls fail fast
  again on hangs.

## v0.4.1 — 2026-05-02

### Bug fixes

- **`crowdsky` uploads** — A flat 30 s HTTP timeout was insufficient
  for ~12 MB stack uploads over slow or long-haul uplinks (e.g. AU
  residential to crowdsky.univie.ac.at). The internal `_request`
  helper now passes `requests` a `(connect, read)` timeout tuple of
  `(30, 300)`, keeping a fast connect bound while giving big uploads
  room to complete.

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
