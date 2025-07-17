import json
from typing import Any, Dict, List


class Event:
    def __init__(self, **kwargs):
        self.meta: Dict[str, Any] = dict(kwargs)
        self.important_attrs: List[str] = ["state", "error"] + getattr(self, 'important_attrs', [])

    def update(self, json_str: str):
        data = json.loads(json_str)
        self.meta.update(data)

    def get_attr(self, name: str) -> Any:
        if name in self.important_attrs:
            return self.meta.get(name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class View(Event):
    important_attrs = ["mode"]


class ScopeTrack(Event):
    pass


class AutoGoto(Event):
    pass


class ScopeGoto(Event):
    important_attrs = ["cur_ra_dec", "dist_deg"]


class Exposure(Event):
    important_attrs = ["exp_ms"]


class PlateSolve(Event):
    important_attrs = ["result"]


class ContinuousExposure(Event):
    pass


class Initialise(Event):
    pass


class DarkLibrary(Event):
    important_attrs = ["percent"]


class WheelMove(Event):
    important_attrs = ["position"]


class PiStatus(Event):
    important_attrs = ["temp", "battery_capacity"]


class AutoFocus(Event):
    important_attrs = ["result"]


class FocuserMove(Event):
    important_attrs = ["position"]


class Stack(Event):
    important_attrs = ["stacked_frame", "dropped_frame"]


class DiskSpace(Event):
    important_attrs = ["used_percent"]


class Annotate(Event):
    pass


class SaveImage(Event):
    important_attrs = ["fullname"]
