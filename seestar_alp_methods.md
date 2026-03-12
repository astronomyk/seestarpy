# Seestar JSON-RPC Method Reference

Compiled from active code in `seestar_alp` (Feb 2026).
Only includes methods with confirmed active usage — legacy/commented-out calls are excluded.

---

## Getters

### `get_albums`
```json
{"method": "get_albums"}
```
No params.

---

### `get_camera_info`
```json
{"method": "get_camera_info"}
```
No params. (Only invoked via Bruno API tests, not in Python device code.)

---

### `get_camera_state`
```json
{"method": "get_camera_state"}
```
No params.

---

### `get_device_state`

**Full state (no filter):**
```json
{"method": "get_device_state"}
```

**Filtered by keys:**
```json
{"method": "get_device_state", "params": {"keys": ["<key1>", "<key2>", ...]}}
```

| Param | Type | Description |
|-------|------|-------------|
| `keys` | `list[str]` | Top-level state keys to return. Known values: `"location_lon_lat"`, `"mount"`, `"device"`, `"setting"`, `"camera"`, `"focuser"`, `"ap"`, `"station"`, `"storage"`, `"balance_sensor"`, `"compass_sensor"`, `"pi_status"` |

---

### `get_disk_volume`
```json
{"method": "get_disk_volume"}
```
No params.

---

### `get_focuser_position`
```json
{"method": "get_focuser_position"}
```
No params. Returns integer position in range ~1200–2600.

---

### `get_last_solve_result`
```json
{"method": "get_last_solve_result"}
```
No params.

---

### `get_solve_result`
```json
{"method": "get_solve_result"}
```
No params.

---

### `get_stacked_img`
```json
{"method": "get_stacked_img"}
```
No params. **Note:** In ALP this is sent over the binary/imaging socket (port 4800) with hardcoded `"id": 23`, not the main command socket (port 4700).

---

### `get_stack_setting`
```json
{"method": "get_stack_setting"}
```
No params.

---

### `get_stack_info`
```json
{"method": "get_stack_info"}
```
No params.

---

### `get_sensor_calibration`
```json
{"method": "get_sensor_calibration"}
```
No params.

---

### `get_setting`
```json
{"method": "get_setting"}
```
No params.

---

### `get_user_location`
```json
{"method": "get_user_location"}
```
No params.

---

### `get_view_state`

**Standard:**
```json
{"method": "get_view_state"}
```

**With explicit id (used for polling loops):**
```json
{"method": "get_view_state", "id": 42}
```

---

### `get_wheel_position`
```json
{"method": "get_wheel_position"}
```
No params.

---

### `get_wheel_setting`
```json
{"method": "get_wheel_setting"}
```
No params.

---

## iscope Commands

### `iscope_get_app_state`
```json
{"method": "iscope_get_app_state"}
```
No params.

---

### `iscope_start_view`

**Goto target (with coordinates):**
```json
{
  "method": "iscope_start_view",
  "params": {
    "mode": "star",
    "target_ra_dec": [<ra>, <dec>],
    "target_name": "<name>",
    "lp_filter": false
  }
}
```

**Mode switch only (no coordinates):**
```json
{"method": "iscope_start_view", "params": {"mode": "star"}}
```

**Frontend passthrough (arbitrary params):**
```json
{"method": "iscope_start_view", "params": <params_from_request>}
```

| Param | Type | Description |
|-------|------|-------------|
| `mode` | `str` | `"star"`, `"moon"`, `"sun"`, `"scenery"` |
| `target_ra_dec` | `[float, float]` | `[RA_hours, Dec_degrees]` |
| `target_name` | `str` | Target name (also used as directory name on emmc) |
| `lp_filter` | `bool` | Always `false` in ALP device code; LP filter controlled via `set_setting` with `stack_lenhance` |

**Note:** ALP never passes a `mosaic` param here. Mosaics are managed at the scheduler level.

---

### `iscope_stop_view`

**Stop everything (full stop):**
```json
{"method": "iscope_stop_view"}
```

**Stop a specific stage:**
```json
{"method": "iscope_stop_view", "params": {"stage": "<stage>"}}
```

| Param | Type | Description |
|-------|------|-------------|
| `stage` | `str` | Stage to stop. Known values: `"AutoGoto"`, `"Stack"`, `"ContinuousExposure"`, `"AutoFocus"`, `"DarkLibrary"`, `"PlateSolve"`, `"ScopeGoto"` |

---

### `iscope_start_stack`
```json
{"method": "iscope_start_stack", "params": {"restart": true}}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `restart` | `bool` | `true` | Restart the stacking sequence |

---

## Scope Commands

### `scope_get_equ_coord`
```json
{"method": "scope_get_equ_coord"}
```
No params. ALP uses `"id": 420` for the heartbeat variant.

---

### `scope_get_horiz_coord`
```json
{"method": "scope_get_horiz_coord"}
```
No params.

---

### `scope_get_ra_dec`
```json
{"method": "scope_get_ra_dec"}
```
No params.

---

### `scope_goto`
```json
{"method": "scope_goto", "params": [<ra>, <dec>]}
```

| Param | Type | Description |
|-------|------|-------------|
| `params[0]` | `float` | RA in decimal hours [0, 24] |
| `params[1]` | `float` | Dec in decimal degrees [-90, 90] |

**Note:** `params` is a list, not a dict.

---

### `scope_move_to_horizon`
```json
{"method": "scope_move_to_horizon"}
```
No params.

---

### `scope_park`

**Simple park:**
```json
{"method": "scope_park"}
```

**With equatorial mode:**
```json
{"method": "scope_park", "params": {"equ_mode": true}}
```

| Param | Type | Description |
|-------|------|-------------|
| `equ_mode` | `bool` | `true` = EQ mode, `false` = Alt-Az mode |

---

### `scope_sync`
```json
{"method": "scope_sync", "params": [<ra>, <dec>]}
```

| Param | Type | Description |
|-------|------|-------------|
| `params[0]` | `float` | RA in decimal hours |
| `params[1]` | `float` | Dec in decimal degrees |

**Note:** `params` is a list, not a dict.

---

### `scope_speed_move`
```json
{
  "method": "scope_speed_move",
  "params": {"speed": <int>, "angle": <int>, "dur_sec": <int>}
}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `speed` | `int` | — | Steps/sec. Max ~4000. 240 = ~1 deg/sec. 0 = stop. |
| `angle` | `int` | — | Direction in degrees. 0=right, 90=up, 180=left, 270=down |
| `dur_sec` | `int` | `3` | Duration in seconds |

---

## Setters

### `set_control_value`
```json
{"method": "set_control_value", "params": ["gain", <int>]}
```

| Param | Type | Description |
|-------|------|-------------|
| `params[0]` | `str` | Control key. Only `"gain"` is used in active code |
| `params[1]` | `int` | Value. For gain: <80 = LCG mode, >=80 = HCG mode |

**Note:** `params` is a list, not a dict.

---

### `set_setting`

Always sends only the specific key(s) being changed:
```json
{"method": "set_setting", "params": {<key>: <value>}}
```

All known setting keys used in ALP active code:

| Key | Type | Example | Description |
|-----|------|---------|-------------|
| `auto_af` | `bool` | `false` | Autofocus after goto |
| `stack_after_goto` | `bool` | `true` | Auto-start stacking after goto completes |
| `exp_ms` | `dict` | `{"stack_l": 10000, "continuous": 500}` | Exposure times in ms. Can send just `stack_l` or both |
| `stack_lenhance` | `bool` | `true` | Enable LP (light pollution) filter / dark subtraction |
| `stack_dither` | `dict` | `{"pix": 50, "interval": 5, "enable": true}` | Dithering settings |
| `stack` | `dict` | `{"dbe": false}` | Stack processing. Known sub-key: `dbe` |
| `frame_calib` | `bool` | `true` | Frame calibration |
| `lang` | `str` | `"en"` | Language |
| `master_cli` | `bool` | `true` | Guest mode / CLI master control |
| `cli_name` | `str` | `"hostname"` | Client hostname identification |
| `auto_3ppa_calib` | `bool` | `true` | Auto 3-point polar alignment calibration |
| `auto_power_off` | `bool` | `false` | Auto power off after inactivity |

Multiple keys can be sent in a single call:
```json
{"method": "set_setting", "params": {"stack": {"dbe": false}, "frame_calib": true}}
```

---

### `set_stack_setting`
```json
{
  "method": "set_stack_setting",
  "params": {
    "save_discrete_ok_frame": true,
    "save_discrete_frame": false
  }
}
```

| Param | Type | Description |
|-------|------|-------------|
| `save_discrete_ok_frame` | `bool` | Save accepted individual sub-frames |
| `save_discrete_frame` | `bool` | Save all individual sub-frames (including rejected) |

---

### `set_sequence_setting`
```json
{"method": "set_sequence_setting", "params": [{"group_name": "<name>"}]}
```

| Param | Type | Description |
|-------|------|-------------|
| `group_name` | `str` | Target/sequence name |

**Note:** `params` is a list containing a single dict.

---

### `set_sensor_calibration`
```json
{
  "method": "set_sensor_calibration",
  "params": {
    "compassSensor": {
      "x": <float>,
      "y": <float>,
      "z": <float>,
      "x11": <float>,
      "x12": <float>,
      "y11": <float>,
      "y12": <float>
    }
  }
}
```

| Param | Type | Description |
|-------|------|-------------|
| `x`, `y`, `z` | `float` | Compass sensor offsets |
| `x11`, `x12`, `y11`, `y12` | `float` | Rotation/calibration matrix coefficients |

---

### `set_user_location`
```json
{
  "method": "set_user_location",
  "params": {"lat": <float>, "lon": <float>, "force": true}
}
```

| Param | Type | Description |
|-------|------|-------------|
| `lat` | `float` | Latitude in decimal degrees (positive = North) |
| `lon` | `float` | Longitude in decimal degrees (positive = East) |
| `force` | `bool` | Always `true` in ALP |

---

### `set_wheel_position`
```json
{"method": "set_wheel_position", "params": [<int>]}
```

| Value | Filter |
|-------|--------|
| `0` | Dark (shutter closed) |
| `1` | IR Cut (open, 400–700nm with Bayer matrix) |
| `2` | LP (narrow-band OIII + H-alpha) |

**Note:** `params` is a list containing a single int.

---

### `move_focuser`
```json
{"method": "move_focuser", "params": {"step": <int>, "ret_step": true}}
```

| Param | Type | Description |
|-------|------|-------------|
| `step` | `int` | Absolute target position (~1200–2600). Factory default: 1580 |
| `ret_step` | `bool` | Always `true` in ALP. Return the final step position |

---

## Pi (System) Commands

### `pi_set_time`
```json
{
  "method": "pi_set_time",
  "params": [{
    "year": <int>,
    "mon": <int>,
    "day": <int>,
    "hour": <int>,
    "min": <int>,
    "sec": <int>,
    "time_zone": "<tz_name>"
  }]
}
```

| Param | Type | Description |
|-------|------|-------------|
| `year` | `int` | e.g. 2026 |
| `mon` | `int` | 1–12 |
| `day` | `int` | 1–31 |
| `hour` | `int` | 0–23 |
| `min` | `int` | 0–59 |
| `sec` | `int` | 0–59 |
| `time_zone` | `str` | IANA timezone name, e.g. `"Europe/Vienna"` |

**Note:** `params` is a list containing a single dict.

---

### `pi_reboot`
```json
{"method": "pi_reboot"}
```
No params. ALP parks the scope before sending this.

---

### `pi_shutdown`
```json
{"method": "pi_shutdown"}
```
No params. ALP parks the scope before sending this.

---

### `pi_is_verified`
```json
{"method": "pi_is_verified"}
```
No params.

---

### `pi_output_set2`
```json
{
  "method": "pi_output_set2",
  "params": {
    "heater": {"state": <bool>, "value": <int>}
  }
}
```

| Param | Type | Description |
|-------|------|-------------|
| `state` | `bool` | Derived from `value > 0` |
| `value` | `int` | Heater power level |

---

## Start/Stop Commands

### `start_auto_focuse`
```json
{"method": "start_auto_focuse"}
```
No params. (Note: misspelling is intentional — matches firmware API.)

---

### `stop_auto_focuse`
```json
{"method": "stop_auto_focuse"}
```
No params.

---

### `start_create_dark`
```json
{"method": "start_create_dark"}
```
No params.

---

### `start_polar_align`
```json
{
  "method": "start_polar_align",
  "params": {"restart": true, "dec_pos_index": <int>}
}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `restart` | `bool` | `true` | Restart the alignment sequence |
| `dec_pos_index` | `int` | from config | Declination position index |

Can also be called without params.

---

### `stop_polar_align`
```json
{"method": "stop_polar_align"}
```
No params.

---

### `start_scan_planet`
```json
{"method": "start_scan_planet"}
```
No params. ALP sends this via `method_async` (non-blocking).

---

### `start_solve`
```json
{"method": "start_solve"}
```
No params.

---

## Misc / Special

### `scan_iscope`
```json
{"id": 1, "method": "scan_iscope", "params": ""}
```
Sent via **UDP** to port 4720 (not TCP). Hardcoded `id: 1`. `params` is an empty string. Used for device discovery/handshake.

---

### `play_sound`
```json
{"method": "play_sound", "params": {"num": <int>}}
```

| Sound ID | Usage in ALP |
|----------|-------------|
| `13` | Before parking for shutdown |
| `80` | Startup sequence begin |
| `82` | Startup complete / scheduler finished |
| `83` | Scheduler manually stopped |

---

### `test_connection`
```json
{"method": "test_connection"}
```
No params. Used as heartbeat in the binary protocol path (port 4800) with hardcoded `"id": 2`. The main command socket heartbeat uses `scope_get_equ_coord` instead.

---

## Methods NOT Found in ALP Active Code

These methods exist in seestarpy but have zero active usage in seestar_alp:

| Method | Notes |
|--------|-------|
| `scope_get_track_state` | Zero references |
| `scope_set_track_state` | Only in a comment: `# method: scope_set_track_state, params: { tracking: true }` |
| `pi_get_time` | Zero references |
| `stop_create_dark` | ALP waits for completion instead of stopping |
| `stop_solve` | Zero references |
| `stop_goto_target` | Not sent as RPC; ALP uses `iscope_stop_view(stage="AutoGoto")` |
| `stop_scheduler` | Not an RPC; ALP manages this locally via `stop_slew()` + `stop_stack()` |
