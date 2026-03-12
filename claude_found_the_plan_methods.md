# Seestar Observation Plan API Reference

Extracted from decompiled Seestar APK v3.0.2.
All commands are sent as JSON over a TCP socket (port 4800) with `\r\n` line termination.

## General Command Format

Every command follows this JSON-RPC style structure:

```json
{"id": <int>, "method": "<method_name>", "params": { ... }}
```

- `id` is a transaction ID (integer) used to correlate requests with responses
- `method` is the API method string
- `params` is an optional object containing method-specific parameters
- Commands without params omit the `params` key entirely

---

## Plan-Related Commands

### Core Plan Execution Commands

These are the commands that control the **active observation plan** (the plan currently running on the device).

#### `set_view_plan` - Start/Set an observation plan

This is the primary command to send a plan to the Seestar and begin executing it.

```json
{
  "id": 1,
  "method": "set_view_plan",
  "params": {
    "plan_name": "My Observation Plan",
    "update_time_seestar": "2026.02.14",
    "list": [
      {
        "target_id": 12345,
        "target_name": "M42",
        "alias_name": "Orion Nebula",
        "target_ra_dec": [83.82, -5.39],
        "lp_filter": true,
        "start_min": 0,
        "duration_min": 30,
        "mosaic": {
          "scale": 1.0,
          "angle": 0.0,
          "star_map_angle": 45.0
        }
      },
      {
        "target_id": 67890,
        "target_name": "M31",
        "alias_name": "Andromeda Galaxy",
        "target_ra_dec": [10.68, 41.27],
        "lp_filter": false,
        "start_min": 30,
        "duration_min": 45
      }
    ]
  }
}
```

Source: `com/zwo/seestar/socket/command/SetViewPlanCmd.java`

#### `get_view_plan` - Get the current active plan

No params needed. Returns a `ViewPlan` object (see Response Format below).

```json
{"id": 2, "method": "get_view_plan"}
```

Source: `com/zwo/seestar/socket/command/GetViewPlanCmd.java`

#### `clear_view_plan` - Stop and clear the active plan

No params needed. Stops the currently executing plan.

```json
{"id": 3, "method": "clear_view_plan"}
```

Source: `com/zwo/seestar/socket/command/ClearViewPlanCmd.java`

### Plan Storage/Management Commands

These manage saved plans on the device. They don't have dedicated command classes in the APK -- they're sent via a generic mechanism, so their exact param formats are inferred from the data models.

| Method | Description | Likely Params |
|--------|-------------|---------------|
| `set_plan` | Save/create a plan on device | `{plan_name, update_time_seestar, list: [...targets]}` |
| `get_plan` | Retrieve a saved plan | `{plan_name}` (inferred) |
| `list_plan` | List all saved plans | none |
| `delete_plan` | Delete a saved plan | `{plan_name}` (inferred) |
| `import_plan` | Import a plan | unknown |
| `reset_plan` | Reset plan progress | `{plan_name}` (inferred) |
| `clear_plan` | Clear a plan | unknown |
| `get_enabled_plan` | Get the currently enabled/active plan | none |

---

## Target Object Format (`PlanTarget`)

Each target in a plan's `list` array has the following structure.

Source: `com/zwoasi/kit/data/PlanTarget.java`

### Fields sent TO the Seestar

| JSON Key | Type | Required | Description |
|----------|------|----------|-------------|
| `target_id` | Long | Yes | Numeric identifier for the target object |
| `target_name` | String | Yes | Catalog name (e.g. `"M42"`, `"NGC 7000"`, `"IC 1396"`) |
| `alias_name` | String | No | Human-friendly display name (e.g. `"Orion Nebula"`) |
| `target_ra_dec` | [Double, Double] | Yes | Right Ascension and Declination as a 2-element array |
| `lp_filter` | Boolean | No | `true` to use the light pollution filter |
| `start_min` | Integer | Yes | Scheduled start time as minutes offset from plan start |
| `duration_min` | Integer | Yes | Observation duration in minutes |
| `mosaic` | Object | No | Mosaic configuration (see below) |

### Mosaic sub-object (`PlanMosaic`)

Source: `com/zwoasi/kit/data/PlanMosaic.java`

| JSON Key | Type | Description |
|----------|------|-------------|
| `scale` | Double | Mosaic scale factor |
| `angle` | Double | Mosaic rotation angle |
| `star_map_angle` | Double | Star map reference angle |

### Fields returned FROM the Seestar (response/events only)

These appear in responses from `get_view_plan` and in plan events but are **not sent** when creating a plan:

| JSON Key | Type | Description |
|----------|------|-------------|
| `state` | String | Target state: see Event States below |
| `error` | String | Error message if the target failed |
| `code` | Integer | Result code (0 = success) |
| `output_file` | Object | Output file info: `{"path": "...", "files": [...]}` |
| `stack_total_sec` | Number | Total seconds of stacking completed |

---

## Response Format (`ViewPlan`)

The response from `get_view_plan` and plan events uses this top-level wrapper:

Source: `com/zwoasi/kit/data/ViewPlan.java`

```json
{
  "code": 0,
  "state": "working",
  "result": {
    "lapse_ms": 5000,
    "state": "working",
    "plan": {
      "plan_name": "My Plan",
      "update_time_seestar": "2026.02.14",
      "list": [
        { ...PlanTarget with state/code/output_file fields... }
      ]
    }
  }
}
```

### Plan Entity (`PlanEntity`)

Source: `com/zwoasi/kit/data/PlanEntity.java`

| JSON Key | Type | Description |
|----------|------|-------------|
| `plan_name` | String | Name of the plan |
| `update_time_seestar` | String | Date string, format `"yyyy.MM.dd"` |
| `list` | Array | Array of `PlanTarget` objects |

---

## Event States

Source: `com/zwoasi/kit/data/EventState.java`

These values appear in `state` fields in responses:

| State | Value | Description |
|-------|-------|-------------|
| IDLE | `"idle"` | Not started / waiting |
| WORKING | `"working"` | Currently executing |
| CANCEL | `"cancel"` | Cancelled by user |
| COMPLETE | `"complete"` | Finished successfully |
| FAIL | `"fail"` | Failed with error |

---

## Plan-Related Events (push notifications from device)

The Seestar pushes status updates as events. Plan-related events:

| Event Name | Value | Description |
|------------|-------|-------------|
| `EVENT_VIEW_PLAN` | `"ViewPlan"` | Plan state changed |
| `EVENT_PLAN_TARGET` | `"Target"` | Individual target state changed |
| `DEVICE_PLAN` | `"device_plan"` | Device plan info |
| `DEVICE_PLAN_UPDATE` | `"device_plan_update"` | Device plan was updated |

---

## Related Commands for Plan Workflow

When building a plan workflow in seestarpy, you'll likely need these supporting commands:

### Before starting a plan

| Method | Description |
|--------|-------------|
| `get_device_state` | Check device is ready |
| `iscope_get_app_state` | Check app/scope state |
| `set_user_location` | Set observer location (lat/long) |
| `test_connection` | Heartbeat / check connection alive |

### During plan execution

| Method | Description |
|--------|-------------|
| `get_view_plan` | Poll plan progress |
| `stop_func` | Stop current function/operation |
| `iscope_start_view` | Start live view |
| `iscope_stop_view` | Stop live view |

### After plan / per-target

| Method | Description |
|--------|-------------|
| `get_stacked_img` | Get the stacked image result |
| `get_img_file_in_jpg` | Download an image as JPG |
| `get_img_thumbnail` | Get image thumbnail |
| `scope_park` | Park the mount (go home) |

---

## Example: Minimal Plan for seestarpy

```python
import json

def create_plan_command(plan_name, targets, transaction_id=1):
    """
    Create a set_view_plan command.

    targets: list of dicts with keys:
        target_id, target_name, target_ra_dec, duration_min
        Optional: alias_name, lp_filter, start_min, mosaic
    """
    from datetime import datetime

    plan_targets = []
    current_start = 0

    for t in targets:
        target = {
            "target_id": t["target_id"],
            "target_name": t["target_name"],
            "target_ra_dec": t["target_ra_dec"],
            "lp_filter": t.get("lp_filter", False),
            "start_min": t.get("start_min", current_start),
            "duration_min": t["duration_min"],
        }
        if "alias_name" in t:
            target["alias_name"] = t["alias_name"]
        if "mosaic" in t:
            target["mosaic"] = t["mosaic"]
        plan_targets.append(target)
        current_start += t["duration_min"]

    cmd = {
        "id": transaction_id,
        "method": "set_view_plan",
        "params": {
            "plan_name": plan_name,
            "update_time_seestar": datetime.now().strftime("%Y.%m.%d"),
            "list": plan_targets,
        }
    }
    return json.dumps(cmd) + "\r\n"
```

---

## Key Source Files

All paths relative to the decompiled output at `D:\Seestar_v3.0.2_decompiled\sources\`:

| File | Contains |
|------|----------|
| `com/zwo/seestar/socket/MainCameraConstants.java` | All ~190 CMD_ and ~70 EVENT_ string constants |
| `com/zwoasi/kit/cmd/CmdMethod.java` | 43-entry command method enum |
| `com/zwo/seestar/socket/command/SetViewPlanCmd.java` | set_view_plan JSON construction |
| `com/zwo/seestar/socket/command/GetViewPlanCmd.java` | get_view_plan JSON construction |
| `com/zwo/seestar/socket/command/ClearViewPlanCmd.java` | clear_view_plan JSON construction |
| `com/zwoasi/kit/data/PlanTarget.java` | PlanTarget data class (Gson serialization) |
| `com/zwoasi/kit/data/PlanEntity.java` | PlanEntity data class (plan wrapper) |
| `com/zwoasi/kit/data/ViewPlan.java` | ViewPlan response data class |
| `com/zwoasi/kit/data/PlanMosaic.java` | PlanMosaic data class |
| `com/zwoasi/kit/data/PlanOutputFile.java` | PlanOutputFile data class |
| `com/zwoasi/kit/data/EventState.java` | Event state enum (idle/working/complete/fail/cancel) |
| `com/zwo/baseui/utils/ConsParam.java` | Shared param key constants (target_name, target_ra_dec) |

---

## Notes

- The `FirebaseAnalytics.Param.METHOD` reference in decompiled code resolves to the string `"method"`
- The `NativeProtocol.WEB_DIALOG_PARAMS` reference resolves to the string `"params"`
- The `TombstoneParser.keyCode` reference resolves to the string `"code"`
- The date format used is `"yyyy.MM.dd"` (e.g. `"2026.02.14"`), not ISO format
- Communication is on TCP port 4800 (`MainCameraConstants.PORT_4800`)
- Commands are terminated with `\r\n` (`IOUtils.LINE_SEPARATOR_WINDOWS`)
