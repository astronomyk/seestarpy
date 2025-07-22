from datetime import datetime as dt

from .connection import send_command
from .raw_commands import (get_device_state, iscope_get_app_state,
                           scope_get_horiz_coord, scope_get_ra_dec, )


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

    dev = get_device_state(["balance_sensor", "mount", "pi_status",
                            "storage"]).get("result", {})
    app = iscope_get_app_state().get("result", {})
    view = app.get("View", {})
    azalt = scope_get_horiz_coord().get("result", ["---", "---"])
    radec = scope_get_ra_dec().get("result", ["---", "---"])

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
    params = {"method": "get_device_state", "params": {"keys":["mount"]}}
    payload = send_command(params)
    return payload["result"]["mount"]


def is_eq_mode():
    return get_mount_state()["equ_mode"]


def is_tracking():
    return get_mount_state()["tracking"]


def is_parked():
    return get_mount_state()["close"]


def get_coords():
    # params = {'method': 'scope_get_equ_coord'}
    params = {'method': 'scope_get_ra_dec'}
    eq_dict = send_command(params)
    params = {'method': 'scope_get_horiz_coord'}
    altaz_dict = send_command(params)

    if (isinstance(eq_dict.get("result"), list) and
            isinstance(altaz_dict.get("result"), list)):
        return {"ra": eq_dict["result"][0],
                "dec": eq_dict["result"][1],
                "alt": altaz_dict["result"][0],
                "az": altaz_dict["result"][1]}
    else:
        raise ValueError(f"Could not get coordinates: {eq_dict}, {altaz_dict}")


def get_exposure(which="stack_l"):
    """which : [stack_l, continuous]"""
    params = {"method": "get_setting", "params": {"keys": ["exp_ms"]}}
    payload = send_command(params)
    return payload["result"]["exp_ms"][which]


def get_filter():
    params = {"method": "get_wheel_position"}
    return send_command(params)


def get_target_name():
    params = {"method": "get_sequence_setting"}
    return send_command(params).get("group_name")


def get_target_name2():
    params = {"method": "get_img_name_field"}
    return send_command(params)


def azimuth_to_compass(degrees):
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW"
    ]
    idx = int((degrees % 360) / 22.5 + 0.5) % 16
    return directions[idx]