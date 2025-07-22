from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class ThreePPA:
    """
    Represents a 3PPA event, related to three-point polar alignment.

    Parameters
    ----------
    state : str
        State of the process. Values: 'start', 'working', 'complete', 'delay1', 'delay2', 'move1', 'move2'
    lapse_ms : int
        Elapsed time in milliseconds.

    Optional Parameters
    -------------------
    percent : float
        Progress percentage. Values: 0.0 to 100.0
    calib_fail_autogoto : bool
        Whether calibration failed to auto-goto. Values: True, False
    offset : list
        Az-Alt offset [x, y] in degrees. Example: [-0.986416, -0.450118]
    equ_offset : list
        Equatorial offset [RA, DEC] in degrees. Example: [-56.145756, 136.862207]
    route : list
        Route stack. Example: ['View']
    state_code : int
        Internal state code. Values: 1, 5, 6, 10, 11
    auto_move : bool
        Whether auto movement is enabled. Values: True, False
    auto_update : bool
        Whether auto update is enabled. Values: True, False
    paused : bool
        Whether the process is paused. Values: True, False
    detail : dict
        Additional detail such as total_ms, lapse_ms
    retry_cnt : int
        Retry count. Values: 0, 1, ...
    """
    state: str
    lapse_ms: int
    percent: Optional[float] = None
    calib_fail_autogoto: Optional[bool] = None
    offset: Optional[List[float]] = field(default_factory=list)
    equ_offset: Optional[List[float]] = field(default_factory=list)
    route: Optional[List[str]] = field(default_factory=list)
    state_code: Optional[int] = None
    auto_move: Optional[bool] = None
    auto_update: Optional[bool] = None
    paused: Optional[bool] = None
    detail: Optional[Dict[str, Any]] = field(default_factory=dict)
    retry_cnt: Optional[int] = None


@dataclass
class AIProcess:
    """
    Represents an AI image processing event.

    Parameters
    ----------
    state : str
        Current state. Values: 'working', 'complete'
    lapse_ms : int
        Elapsed time in ms.

    Optional Parameters
    -------------------
    ori_name : str
        Original image filename. Example: 'ori_path.jpg'
    dst_name : str
        Destination image filename. Example: 'dst_path.jpg'
    route : list
        Contextual route. Example: ['View']
    """
    state: str
    lapse_ms: int
    ori_name: Optional[str] = None
    dst_name: Optional[str] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class Alert:
    """
    Represents alerts raised during operations.

    Parameters
    ----------
    error : str
        Description of the error. Values: 'below horizon', 'stack error, too few stars', 'stack error, transform failed', 'star trails'
    code : int
        Numeric error code. Values: 263, 264, 270, 530
    """
    error: str
    code: int


@dataclass
class Annotate:
    """
    Represents image annotation processes.

    Parameters
    ----------
    state : str
        Status of the annotation. Values: 'start', 'working', 'complete'

    Optional Parameters
    -------------------
    page : str
        Page context. Values: 'stack'
    lapse_ms : int
        Time taken for annotation.
    result : dict
        Annotation results including object metadata.
    route : list
        UI route. Example: ['View', 'Stack']
    """
    state: str
    page: Optional[str] = None
    lapse_ms: Optional[int] = None
    result: Optional[Dict[str, Any]] = field(default_factory=dict)
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class AutoFocus:
    """
    Represents autofocus operations and outcomes.

    Parameters
    ----------
    state : str
        Autofocus state. Values: 'start', 'working', 'fail'

    Optional Parameters
    -------------------
    lapse_ms : int
        Elapsed time in milliseconds.
    error : str
        Description of error if failed. Values: 'no star is detected'
    code : int
        Numeric error code. Values: 279
    route : list
        Route context. Example: ['View']
    result : dict
        Result of focus scan (scale, points, etc).
    """
    state: str
    lapse_ms: Optional[int] = None
    error: Optional[str] = None
    code: Optional[int] = None
    route: Optional[List[str]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = field(default_factory=dict)


from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class AutoGoto:
    """
    Represents an AutoGoto operation.

    Parameters
    ----------
    state : str
        State of the goto process. Values: 'start', 'working', 'complete', 'fail'

    Optional Parameters
    -------------------
    page : str
        UI page. Values: 'preview'
    tag : str
        UI tag. Values: 'Exposure'
    func : str
        Function executed. Values: 'goto_ra_dec'
    error : str
        Error reason. Values: 'mount goto failed', 'solve failed'
    code : int
        Error code. Values: 251, 501
    target_ra_dec : list
        Target coordinates in RA/DEC. Example: [13.4, 54.900002]
    target_name : str
        Name of the target. Example: 'Mizar'
    lapse_ms : int
        Elapsed time in milliseconds.
    count : int
        Retry or step count.
    hint : bool
        Whether a hint was used. Values: True, False
    route : list
        UI route. Examples: ['View'], ['View', '3PPA']
    """
    state: str
    page: Optional[str] = None
    tag: Optional[str] = None
    func: Optional[str] = None
    error: Optional[str] = None
    code: Optional[int] = None
    target_ra_dec: Optional[List[float]] = field(default_factory=list)
    target_name: Optional[str] = None
    lapse_ms: Optional[int] = None
    count: Optional[int] = None
    hint: Optional[bool] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class AutoGotoStep:
    """
    Represents a step in the AutoGoto sequence.

    Parameters
    ----------
    state : str
        Status of the step. Values: 'fail'

    Optional Parameters
    -------------------
    page : str
        UI page. Values: 'preview'
    tag : str
        UI tag. Values: 'Exposure'
    func : str
        Function name. Values: 'goto_ra_dec'
    count : int
        Step or retry count. Example: 6
    error : str
        Error reason. Values: 'mount goto failed'
    code : int
        Error code. Values: 501
    """
    state: str
    page: Optional[str] = None
    tag: Optional[str] = None
    func: Optional[str] = None
    count: Optional[int] = None
    error: Optional[str] = None
    code: Optional[int] = None


@dataclass
class BalanceSensor:
    """
    Represents data from the balance sensor.

    Parameters
    ----------
    code : int
        Status code. Values: 0

    Optional Parameters
    -------------------
    data : dict
        Balance data with x, y, z acceleration and angle. Example: {'x': 0.316085, 'y': -0.515709, 'z': 1.104264, 'angle': 28.712015}
    """
    code: int
    data: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ContinuousExposure:
    """
    Represents a continuous exposure stream.

    Parameters
    ----------
    state : str
        Current state. Values: 'cancel', 'working'

    Optional Parameters
    -------------------
    lapse_ms : int
        Duration in milliseconds.
    fps : float
        Frames per second. Example: 2.024457
    route : list
        Route in the UI. Example: ['View']
    """
    state: str
    lapse_ms: Optional[int] = None
    fps: Optional[float] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class DarkLibrary:
    """
    Represents the dark frame library creation process.

    Parameters
    ----------
    state : str
        Process state. Values: 'working', 'complete'

    Optional Parameters
    -------------------
    lapse_ms : int
        Time in milliseconds.
    percent : float
        Completion percentage. Example: 100.0
    route : list
        UI route. Example: ['View', 'Initialise']
    """
    state: str
    lapse_ms: Optional[int] = None
    percent: Optional[float] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class DiskSpace:
    """
    Represents the current disk space usage.

    Parameters
    ----------
    used_percent : int
        Used space percentage. Example: 38
    """
    used_percent: int


from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Exposure:
    """
    Represents an exposure capture operation.

    Parameters
    ----------
    state : str
        Current state of the exposure. Values: 'start', 'working', 'downloading', 'complete', 'fail', 'cancel'

    Optional Parameters
    -------------------
    page : str
        UI context. Values: 'preview', 'stack'
    tag : str
        Tag for identifying exposure type. Example: 'Exposure-AutoGoto'
    ac_count : int
        Auto capture count. Example: 1
    exp_us : int
        Exposure time in microseconds. Example: 2000000, 10000000
    gain : int
        Gain setting. Example: 80
    error : str
        Error description. Values: 'interrupt'
    code : int
        Error code. Values: 514
    lapse_ms : int
        Elapsed time in milliseconds.
    exp_ms : float
        Exposure duration in milliseconds. Example: 1000.0, 2000.0, 10000.0
    route : list
        Route path. Examples: ['View', 'Stack'], ['View', 'AutoFocus']
    """
    state: str
    page: Optional[str] = None
    tag: Optional[str] = None
    ac_count: Optional[int] = None
    exp_us: Optional[int] = None
    gain: Optional[int] = None
    error: Optional[str] = None
    code: Optional[int] = None
    lapse_ms: Optional[int] = None
    exp_ms: Optional[float] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class FocuserMove:
    """
    Represents a focuser movement operation.

    Parameters
    ----------
    state : str
        State of the focuser. Values: 'complete', 'working'

    Optional Parameters
    -------------------
    lapse_ms : int
        Time in milliseconds.
    position : int
        Final position. Examples: 0, 1540, 1580, 1820
    route : list
        UI route. Examples: ['View', 'AutoFocus']
    """
    state: str
    lapse_ms: Optional[int] = None
    position: Optional[int] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class GSensorMove:
    """
    Represents G-sensor activity.

    Parameters
    ----------
    Timestamp : str
        Time the movement was registered. Example: '2205.182986165'
    """
    Timestamp: str


@dataclass
class Initialise:
    """
    Represents the initialization state of the device.

    Parameters
    ----------
    Timestamp : str
        Time the init occurred. Example: '718.139747786'
    state : str
        Status of initialization. Values: 'working', 'complete'

    Optional Parameters
    -------------------
    lapse_ms : int
        Elapsed time.
    route : list
        Route context. Example: ['View']
    """
    Timestamp: str
    state: str
    lapse_ms: Optional[int] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class MountMode:
    """
    Represents equatorial mount mode status.

    Parameters
    ----------
    Timestamp : str
        Event timestamp. Example: '1902.412544972'
    equ_mode : bool
        Whether equatorial mode is enabled. Values: True, False
    """
    Timestamp: str
    equ_mode: bool


@dataclass
class MoveByAngle:
    """
    Represents movement by a specific angle.

    Parameters
    ----------
    state : str
        State of the movement. Values: 'start', 'moving', 'complete'

    Optional Parameters
    -------------------
    value : float
        Angle in degrees. Example: 10.043414
    """
    state: str
    value: Optional[float] = None


@dataclass
class PiStatus:
    """
    Represents Pi hardware status.

    Optional Parameters
    -------------------
    temp : float
        Temperature in Celsius. Example: 46.5
    battery_temp : int
        Battery temperature. Example: 27
    battery_capacity : int
        Battery percentage. Example: 42
    charger_status : str
        Charging state. Values: 'Discharging'
    """
    temp: Optional[float] = None
    battery_temp: Optional[int] = None
    battery_capacity: Optional[int] = None
    charger_status: Optional[str] = None


from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class PlateSolve:
    """
    Represents plate solving events.

    Parameters
    ----------
    state : str
        Current solving state. Values: 'start', 'solving', 'working', 'complete', 'fail'

    Optional Parameters
    -------------------
    page : str
        Context page. Values: 'preview', 'stack'
    tag : str
        Exposure tag. Example: 'Exposure-AutoGoto'
    ac_count : int
        Auto capture count. Example: 1
    error : str
        Error message. Values: 'solve failed'
    code : int
        Error code. Values: 251
    lapse_ms : int
        Time elapsed in ms. Example: 3169, 30964
    star_number : int
        Number of stars detected. Examples: 2148, 429, 6802
    ra_dec : list
        Right Ascension and Declination. Example: [14.328956, 19.398779]
    fov : list
        Field of view in degrees. Example: [0.711682, 1.265403]
    focal_len : float
        Focal length in mm. Example: 252.111633
    angle : float
        Rotation angle in degrees. Example: 308.333008
    image_id : int
        Image identifier. Example: 852
    result : dict
        Plate solve result details.
    route : list
        Route in UI. Examples: ['View', 'AutoGoto']
    """
    state: str
    page: Optional[str] = None
    tag: Optional[str] = None
    ac_count: Optional[int] = None
    error: Optional[str] = None
    code: Optional[int] = None
    lapse_ms: Optional[int] = None
    star_number: Optional[int] = None
    ra_dec: Optional[List[float]] = field(default_factory=list)
    fov: Optional[List[float]] = field(default_factory=list)
    focal_len: Optional[float] = None
    angle: Optional[float] = None
    image_id: Optional[int] = None
    result: Optional[Dict[str, Any]] = field(default_factory=dict)
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class SaveImage:
    """
    Represents the result of saving an image.

    Parameters
    ----------
    state : str
        Save state. Values: 'complete'

    Optional Parameters
    -------------------
    filename : str
        File name only. Example: 'Stacked_36_Polaris_10.0s_IRCUT_20250720-224643.fit'
    fullname : str
        Full path name. Example: 'MyWorks/Polaris/Stacked_36_Polaris_10.0s_IRCUT_20250720-224643.fit'
    """
    state: str
    filename: Optional[str] = None
    fullname: Optional[str] = None


@dataclass
class ScopeGoto:
    """
    Represents telescope movement to RA/DEC coordinates.

    Parameters
    ----------
    state : str
        Movement state. Values: 'complete', 'fail', 'working'

    Optional Parameters
    -------------------
    lapse_ms : int
        Time taken for goto in ms.
    cur_ra_dec : list
        Current RA/DEC position. Example: [13.399722, 54.9]
    dist_deg : float
        Distance in degrees to target. Example: 0.002394, 123.233118
    error : str
        Error message. Values: 'mount goto failed'
    code : int
        Error code. Values: 501
    route : list
        UI path. Example: ['View', 'AutoGoto']
    """
    state: str
    lapse_ms: Optional[int] = None
    cur_ra_dec: Optional[List[float]] = field(default_factory=list)
    dist_deg: Optional[float] = None
    error: Optional[str] = None
    code: Optional[int] = None
    route: Optional[List[str]] = field(default_factory=list)


from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class ScopeHome:
    """
    Represents the scope homing process.

    Parameters
    ----------
    state : str
        State of homing. Values: 'complete', 'working'

    Optional Parameters
    -------------------
    lapse_ms : int
        Time taken for the homing process in ms.
    close : bool
        Whether the process was a close action. Values: True, False
    equ_mode : bool
        Equatorial mode state. Values: True, False
    """
    state: str
    lapse_ms: Optional[int] = None
    close: Optional[bool] = None
    equ_mode: Optional[bool] = None


@dataclass
class ScopeMoveToHorizon:
    """
    Represents telescope move to horizon.

    Parameters
    ----------
    state : str
        Status of movement. Values: 'complete', 'working'

    Optional Parameters
    -------------------
    lapse_ms : int
        Time in milliseconds.
    close : bool
        Whether to close after movement. Values: True, False
    """
    state: str
    lapse_ms: Optional[int] = None
    close: Optional[bool] = None


@dataclass
class ScopeTrack:
    """
    Represents telescope tracking state.

    Parameters
    ----------
    state : str
        Tracking status. Values: 'on', 'off'

    Optional Parameters
    -------------------
    tracking : bool
        Whether tracking is active. Values: True, False
    manual : bool
        Manual tracking toggle. Values: True, False
    error : str
        Error message. Values: 'below horizon', 'equipment is moving', 'fail to operate', 'mount sync failed'
    code : int
        Error code. Values: 203, 207, 270, 502
    route : list
        Route path. Example: []
    """
    state: str
    tracking: Optional[bool] = None
    manual: Optional[bool] = None
    error: Optional[str] = None
    code: Optional[int] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class Stack:
    """
    Represents the image stacking process.

    Parameters
    ----------
    state : str
        State of the stacking. Values: 'start', 'working', 'cancel', 'frame_complete'

    Optional Parameters
    -------------------
    lapse_ms : int
        Time elapsed in milliseconds.
    frame_errcode : int
        Frame error code. Values: -1, 0, 263, 530
    stacked_frame : int
        Number of frames stacked.
    dropped_frame : int
        Number of dropped frames.
    total_frame : int
        Total frames received.
    frame_type : str
        Type of frame. Example: 'light'
    error : str
        Error message. Examples: 'stack error, too few stars', 'star trails', 'no error'
    code : int
        Error code. Examples: 0, 263, 530
    can_annotate : bool
        Whether annotation is available. Values: True, False
    jpg_name : str
        JPEG output filename.
    route : list
        Route in UI. Example: ['View']
    """
    state: str
    lapse_ms: Optional[int] = None
    frame_errcode: Optional[int] = None
    stacked_frame: Optional[int] = None
    dropped_frame: Optional[int] = None
    total_frame: Optional[int] = None
    frame_type: Optional[str] = None
    error: Optional[str] = None
    code: Optional[int] = None
    can_annotate: Optional[bool] = None
    jpg_name: Optional[str] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class View:
    """
    Represents a view operation on a target.

    Parameters
    ----------
    state : str
        View state. Values: 'cancel', 'working'

    Optional Parameters
    -------------------
    lapse_ms : int
        Elapsed time.
    mode : str
        View mode. Example: 'star'
    cam_id : int
        Camera ID. Example: 0
    target_ra_dec : list
        Target RA/DEC coordinates. Example: [13.4, 54.900002]
    target_name : str
        Target name. Example: 'Mizar'
    lp_filter : bool
        Whether LP filter is applied. Values: True, False
    gain : int
        Gain level. Example: 80
    route : list
        Route context. Example: []
    """
    state: str
    lapse_ms: Optional[int] = None
    mode: Optional[str] = None
    cam_id: Optional[int] = None
    target_ra_dec: Optional[List[float]] = field(default_factory=list)
    target_name: Optional[str] = None
    lp_filter: Optional[bool] = None
    gain: Optional[int] = None
    route: Optional[List[str]] = field(default_factory=list)


@dataclass
class WheelMove:
    """
    Represents movement of the filter wheel.

    Parameters
    ----------
    state : str
        Movement state. Values: 'start', 'complete'

    Optional Parameters
    -------------------
    position : int
        Position index. Examples: 0, 1
    """
    state: str
    position: Optional[int] = None
