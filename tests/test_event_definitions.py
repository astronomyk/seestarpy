import json
import pytest
from src.seestarpy.events import event_definitions as ed

# Sample log lines from user input (stringified for test simulation)
TEST_LOG_LINES = [
    '{"event": "3PPA", "state": "complete", "lapse_ms": 74605, "percent": 99.0, "calib_fail_autogoto": false, "offset": [-0.986416, -0.450118], "equ_offset": [-56.145756, 136.862207], "route": ["View"]}',
    '{"event": "AIProcess", "state": "working", "lapse_ms": 0, "route": []}',
    '{"event": "Alert", "error": "below horizon", "code": 270}',
    '{"event": "Annotate", "page": "stack", "state": "complete", "result": {"image_size": [1080, 1920], "annotations": [{"type": "ngc", "names": ["NGC 6341", "M 92"], "pixelx": 578.106, "pixely": 991.061, "radius": 182.05}], "image_id": 1425}}',
    '{"event": "AutoFocus", "state": "fail", "error": "no star is detected", "code": 279, "lapse_ms": 24182, "route": ["View", "Initialise"]}',
    '{"event": "AutoGoto", "page": "preview", "tag": "Exposure", "func": "goto_ra_dec", "state": "fail", "error": "mount goto failed", "code": 501}',
    '{"event": "DiskSpace", "used_percent": 38}',
    '{"event": "Exposure", "page": "preview", "state": "start", "exp_us": 2000000, "gain": 80}',
    '{"event": "FocuserMove", "state": "working", "lapse_ms": 0, "position": 1540, "route": ["View", "AutoFocus"]}',
    '{"event": "GSensorMove", "Timestamp": "2205.182986165"}',
    '{"event": "Initialise", "Timestamp": "718.139747786", "state": "working", "lapse_ms": 0, "route": ["View"]}',
    '{"event": "MountMode", "Timestamp": "1902.412544972", "equ_mode": false}',
    '{"event": "MoveByAngle", "state": "moving", "value": 10.043414}',
    '{"event": "PiStatus", "battery_capacity": 42}',
    '{"event": "PlateSolve", "state": "fail", "error": "solve failed", "code": 251, "lapse_ms": 30961, "route": ["View", "Stack"]}',
    '{"event": "SaveImage", "state": "complete", "filename": "Stacked_36_Polaris.fit", "fullname": "MyWorks/Polaris/Stacked_36_Polaris.fit"}',
    '{"event": "ScopeGoto", "state": "complete", "lapse_ms": 1052, "cur_ra_dec": [13.399722, 54.9], "dist_deg": 0.002394, "route": ["View", "AutoGoto"]}',
    '{"event": "ScopeTrack", "state": "off", "tracking": false, "manual": false, "error": "below horizon", "code": 270, "route": []}',
    '{"event": "Stack", "state": "start"}',
    '{"event": "View", "state": "working", "lapse_ms": 0, "mode": "star", "cam_id": 0, "target_ra_dec": [12.0, 70.0], "target_name": "Servus", "lp_filter": false, "gain": 80, "route": []}',
    '{"event": "WheelMove", "state": "start"}'
]
with open("event_output_20250722.dat") as f:
    TEST_LOG_LINES = [s.strip() for s in f.readlines()]


@pytest.mark.parametrize("json_str", TEST_LOG_LINES)
def test_event_class_from_json(json_str):
    json_str = json_str.replace("3PPA", "ThreePPA").replace("'", '"')
    json_str = json_str.replace("True", '"True"').replace("False", '"False"')
    data = json.loads(json_str)
    event_type = data["event"]
    event_kwargs = {k: v for k, v in data.items() if k != "event"}

    # Locate the class in any of the modules
    cls = getattr(ed, event_type, None)
    if cls is None:
        raise ImportError(f"No class found for event type: {event_type}")

    # Instantiate and compare fields
    obj = cls(**event_kwargs)
    for key, value in event_kwargs.items():
        actual_value = getattr(obj, key)
        assert actual_value == value, f"Mismatch in field '{key}' for event '{event_type}'"
