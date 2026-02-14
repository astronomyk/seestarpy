from datetime import datetime as dt

from . import raw
from .connection import send_command


def status_bar(return_type="str"):
    """
    Generate a structured ASCII-style status bar for Seestar state display.

    Parameters
    ----------
    return_type : str
        ["str", "dict"] Return the CLI-formatted status bar as a string or
        a dictionary with all the entries

    Returns
    -------
    str or dict
        A multi-line string formatted for CLI or Jupyter display.

|================|================|================|================|==========|
| View           | Coordinates    | Observation    | Initialisation | Seestar  |
|================|================|================|================|==========|
| MODE           | TARGET RA/DEC  | LP_FILTER      | DARK           | BATTERY  |
| "star"         | hh.hhh  dd.dd  | True           | 100%           | 100%     |
|----------------|----------------|----------------|----------------|----------|
| STATE          | CURRENT RA/DEC | EXPTIME        | FOCUS POS      | FREE MB  |
| "ContinuousEx" | hh.hhh  dd.dd  | 10             | 1605           | 40000    |
|----------------|----------------|----------------|----------------|----------|
| ERROR          | AZ      AZ     | STACK    DROP  | PLATESOLVE     | EQ_MODE  |
| "Fail to move" | ddd.dd  dd.dd  | sssss    dddd  | x.xx y.yy      | False    |
|----------------|----------------|----------------|----------------|----------|
| NAME           | BALANCE ANGLE  | TRACKING       | LAST UPDATE               |
| "Mizar"        | dd.dd          | True           | hh:mm:ss  (sss sec ago)   |
|================|================|================|================|==========|

    """

    dev = raw.get_device_state(["balance_sensor", "mount", "pi_status",
                            "storage"]).get("result", {})
    app = raw.iscope_get_app_state().get("result", {})
    view = app.get("View", {})
    azalt = raw.scope_get_horiz_coord().get("result", ["---", "---"])
    radec = raw.scope_get_ra_dec().get("result", ["---", "---"])

    t11 = f'{view.get("mode", "---"):^14}'
    t12 = f'{view.get("state", "---"):^14}'
    t13 = f'{view.get("error", "---"):^14}'
    t14 = f'{view.get("target_name", "---"):^14}'

    t21a = f'{round(view.get("target_ra_dec", ["---", "---"])[0], 3):<7}'
    t21b = f'{round(view.get("target_ra_dec", ["---", "---"])[1], 2):<6}'
    t22a = f'{round(radec[0], 3):<7}'
    t22b = f'{round(radec[1], 2):<6}'
    al = f'{round(azalt[0]):<4}'
    az = f'{round(azalt[1]):<4}'
    co = f'{azimuth_to_compass(azalt[1]):<4}'
    t24 = f'{round(dev.get("balance_sensor", {}).get("data", {}).get("angle", "---"), 3):^14}'

    t31 = f'{str(view.get("lp_filter")):^14}'
    t32 = f'{view.get("Stack", {}).get("Exposure", {}).get("exp_ms", 0)/1000:^14}'
    t33a = f'{view.get("Stack", {}).get("stacked_frame", "---"):<6}'
    t33b = f'{view.get("Stack", {}).get("dropped_frame", "---"):<6}'
    t34 = f'{str(dev.get("mount", {}).get("tracking")):^14}'

    t41 = f'{app.get("DarkLibrary", {}).get("percent", "---"):^14}'
    t42 = f'{app.get("FocuserMove", {}).get("position", "---"):^14}'
    t43 = f'{app.get("PlateSolve", view.get("Stack", {}).get("PlateSolve",{})).get("state", "---"):^14}'
    t44 = f'{app.get("PlateSolve", view.get("Stack", {}).get("PlateSolve",{})).get("error", "---"):^14}'

    t51 = f'{str(dev.get("pi_status", {}).get("battery_capacity"))+"%":^7}'
    t52 = f'{dev.get("storage", {}).get("storage_volume", [{}])[0].get("free_mb", "---"):^8}'
    t53 = f'{str(dev.get("mount", {}).get("equ_mode")):^8}'
    t54 = f'{dt.now().strftime("%H:%M:%S"):^8}'

    return f"""
|================|================|================|================|==========|
| View           | Coordinates    | Observation    | Initialisation | Seestar  |
|================|================|================|================|==========|
|      MODE      | TARGET RA/DEC  |   LP FILTER    |   DARK FRAME   | BATTERY  |
| {t11         } | {t21a } {t21b} | {t31         } | {t41         } | {t51   } |
|----------------|----------------|----------------|----------------|----------|
|     STATE      | CURRENT RA/DEC | EXPOSURE TIME  | FOCUS POSITION | FREE MB  |
| {t12         } | {t22a } {t22b} | {t32         } | {t42         } | {t52   } |
|----------------|----------------|----------------|----------------|----------|
|     ERROR      | ALT   AZ  COMP | STACK    DROP  |   PLATE SOLVE  | EQ_MODE  |
| {t13         } | {al} {az} {co} | {t33a}   {t33b}| {t43         } | {t53   } |
|----------------|----------------|----------------|----------------|----------|
|  TARGET NAME   | BALANCE ANGLE  |    TRACKING    |  SOLVE ERROR   |   TIME   |
| {t14         } | {t24         } | {t34         } | {t44         } | {t54   } |
|================|================|================|================|==========|
"""


def get_mount_state():
    """
    Get the current mount state dictionary.

    Returns
    -------
    dict
        Mount state containing keys like ``'move_type'``, ``'close'``,
        ``'tracking'``, ``'equ_mode'``.
    """
    return raw.get_device_state(keys=["mount"]).get("result", {}).get("mount", {})


def is_eq_mode():
    """
    Check whether the mount is in equatorial mode.

    Returns
    -------
    bool
    """
    return get_mount_state().get("equ_mode")


def is_tracking():
    """
    Check whether the mount is currently tracking.

    Returns
    -------
    bool
    """
    return get_mount_state().get("tracking")


def is_parked():
    """
    Check whether the mount is parked (arm closed).

    Returns
    -------
    bool
    """
    return get_mount_state().get("close")


def get_coords():
    """
    Get the current equatorial and horizontal coordinates.

    Returns
    -------
    dict
        Dictionary with keys ``'ra'``, ``'dec'``, ``'alt'``, ``'az'``.

    Raises
    ------
    ValueError
        If the coordinate data cannot be retrieved.
    """
    eq_dict = raw.scope_get_ra_dec()
    altaz_dict = raw.scope_get_horiz_coord()

    if (isinstance(eq_dict.get("result"), list) and
            isinstance(altaz_dict.get("result"), list)):
        return {"ra": eq_dict["result"][0],
                "dec": eq_dict["result"][1],
                "alt": altaz_dict["result"][0],
                "az": altaz_dict["result"][1]}
    else:
        raise ValueError(f"Could not get coordinates: {eq_dict}, {altaz_dict}")


def get_exposure(which="stack_l"):
    """
    Get the current exposure time in milliseconds.

    Parameters
    ----------
    which : str, optional
        Which exposure to query. One of ``'stack_l'`` or ``'continuous'``.
        Default is ``'stack_l'``.

    Returns
    -------
    int
        Exposure time in milliseconds.
    """
    params = {"method": "get_setting", "params": {"keys": ["exp_ms"]}}
    payload = send_command(params)
    return payload["result"]["exp_ms"][which]


def get_filter():
    """
    Get the current filter-wheel position.

    Returns
    -------
    dict
    """
    params = {"method": "get_wheel_position"}
    return send_command(params)


def get_target_name():
    """
    Get the current observation sequence (group) name.

    Returns
    -------
    str or None
        The group name, or ``None`` if not set.
    """
    params = {"method": "get_sequence_setting"}
    return send_command(params).get("group_name")


def get_target_name2():
    """
    Get the current image name field.

    Returns
    -------
    dict
    """
    params = {"method": "get_img_name_field"}
    return send_command(params)


def azimuth_to_compass(degrees):
    """
    Convert an azimuth angle to a 16-point compass direction.

    Parameters
    ----------
    degrees : float
        Azimuth in decimal degrees [0, 360).

    Returns
    -------
    str
        Compass direction, e.g. ``'N'``, ``'NNE'``, ``'SW'``.
    """
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW"
    ]
    idx = int((degrees % 360) / 22.5 + 0.5) % 16
    return directions[idx]