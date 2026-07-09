from datetime import datetime as dt

from . import raw
from .connection import send_command, multiple_ips


def _num(val, nd=None):
    """Round *val* for display, or return ``"---"`` if it isn't numeric.

    ``status_bar`` populates its cells from live device queries.  When an
    endpoint returns an error dict (e.g. an unknown RPC method on newer
    firmware) the corresponding value is a placeholder string rather than a
    number, and calling ``round()`` on it would raise ``TypeError``.  This
    helper keeps the dashboard rendering gracefully in that case.
    """
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return "---"
    return round(val, nd) if nd is not None else round(val)


def _pair(resp, keys):
    """Extract a two-element coordinate ``[a, b]`` from a coordinate RPC.

    The firmware return shape is **version dependent**: newer firmware
    replies with a dict (e.g. ``scope_get_equ_coord`` -> ``{"ra": .., "dec":
    ..}``), while older firmware replied with a bare list ``[a, b]``.  This
    tolerates both (and error responses, which lack ``result``), always
    returning a two-element list so callers can index ``[0]``/``[1]``.

    Parameters
    ----------
    resp : dict
        The raw RPC response.
    keys : tuple of str
        The dict keys to read for the (first, second) element, e.g.
        ``("ra", "dec")`` or ``("alt", "az")``.
    """
    result = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(result, dict):
        return [result.get(keys[0], "---"), result.get(keys[1], "---")]
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        return [result[0], result[1]]
    return ["---", "---"]


@multiple_ips
def status_bar(return_type="str"):
    """
    Query the Seestar and return a formatted ASCII status dashboard.

    Pulls data from multiple device endpoints (device state, app state,
    coordinates) and combines them into a single table.  Useful for
    quick at-a-glance monitoring in a terminal or Jupyter notebook.

    Parameters
    ----------
    return_type : str, optional
        Output format.  ``"str"`` (default) returns a printable multi-line
        string; ``"dict"`` returns the raw values as a dictionary.

    Returns
    -------
    str or dict
        The formatted status table, or a dictionary of all queried values.

    Notes
    -----
    The table layout is shown below.  Each cell is populated from live
    device queries::

        |================|================|================|================|==========|
        | View           | Coordinates    | Observation    | Initialisation | Seestar  |
        |================|================|================|================|==========|
        | MODE           | TARGET RA/DEC  | LP FILTER      | DARK FRAME     | BATTERY  |
        | STATE          | CURRENT RA/DEC | EXPOSURE TIME  | FOCUS POSITION | FREE MB  |
        | ERROR          | ALT  AZ  COMP  | STACK    DROP  | PLATE SOLVE    | EQ_MODE  |
        | TARGET NAME    | BALANCE ANGLE  | TRACKING       | SOLVE ERROR    | TIME     |
        |================|================|================|================|==========|

    Examples
    --------

        >>> from seestarpy import status
        >>> print(status.status_bar())

    """

    dev = raw.get_device_state(["balance_sensor", "mount", "pi_status",
                            "storage"]).get("result", {})
    app = raw.iscope_get_app_state().get("result", {})
    view = app.get("View", {})
    azalt = _pair(raw.scope_get_horiz_coord(), ("alt", "az"))
    # ``scope_get_equ_coord`` is the command-socket (port 4700) RA/Dec method
    # used by the official app on all firmware; ``scope_get_ra_dec`` is a
    # port-4800 heartbeat and is rejected on the command socket by newer
    # firmware (v8.x), which used to crash this dashboard.  Newer firmware
    # returns RA/Dec as a dict ({"ra":.., "dec":..}); older firmware returned
    # a list -- _pair() normalises both.
    radec = _pair(raw.scope_get_equ_coord(), ("ra", "dec"))

    t11 = f'{view.get("mode", "---"):^14}'
    t12 = f'{view.get("state", "---"):^14}'
    t13 = f'{view.get("error", "---"):^14}'
    t14 = f'{view.get("target_name", "---"):^14}'

    target_ra_dec = view.get("target_ra_dec", ["---", "---"])
    t21a = f'{_num(target_ra_dec[0], 3):<7}'
    t21b = f'{_num(target_ra_dec[1], 2):<6}'
    t22a = f'{_num(radec[0], 3):<7}'
    t22b = f'{_num(radec[1], 2):<6}'
    al = f'{_num(azalt[0]):<4}'
    az = f'{_num(azalt[1]):<4}'
    co = f'{(azimuth_to_compass(azalt[1]) if isinstance(azalt[1], (int, float)) and not isinstance(azalt[1], bool) else "---"):<4}'
    t24 = f'{_num(dev.get("balance_sensor", {}).get("data", {}).get("angle", "---"), 3):^14}'

    t31 = f'{str(view.get("lp_filter")):^14}'
    t32 = f'{view.get("Stack", {}).get("Exposure", {}).get("exp_ms", 0)/1000:^14}'
    t33a = f'{view.get("Stack", {}).get("stacked_frame", "---"):<6}'
    t33b = f'{view.get("Stack", {}).get("dropped_frame", "---"):<6}'
    t34 = f'{str(dev.get("mount", {}).get("tracking")):^14}'

    t41 = f'{app.get("DarkLibrary", {}).get("percent", "---"):^14}'
    t42 = f'{app.get("FocuserMove", {}).get("position", "---"):^14}'
    t43 = f'{app.get("PlateSolve", view.get("PlateSolve", {}).get("PlateSolve",{})).get("state", "---"):^14}'
    t44 = f'{app.get("PlateSolve", view.get("PlateSolve", {}).get("PlateSolve",{})).get("error", "---"):^14}'

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


@multiple_ips
def get_firmware_version():
    """
    Get the Seestar firmware version string.

    Returns
    -------
    str
        Firmware version, e.g. ``"7.18"``.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_firmware_version()
        '7.18'

    """
    return (raw.get_device_state(["device"])
            .get("result", {})
            .get("device", {})
            .get("firmware_ver_string"))


@multiple_ips
def get_mount_state():
    """
    Get the full mount state dictionary from the Seestar.

    This is a convenience wrapper around
    ``raw.get_device_state(keys=["mount"])``, returning just the
    ``mount`` sub-dictionary.

    Returns
    -------
    dict
        Mount state with keys:

        - ``'move_type'`` (str) — e.g. ``"none"``, ``"tracking"``.
        - ``'close'`` (bool) — ``True`` when the arm is parked.
        - ``'tracking'`` (bool) — ``True`` when sidereal tracking is on.
        - ``'equ_mode'`` (bool) — ``True`` when in equatorial-mount mode.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_mount_state()
        {'move_type': 'none', 'close': False, 'tracking': True, 'equ_mode': True}

    """
    return raw.get_device_state(keys=["mount"]).get("result", {}).get("mount", {})


@multiple_ips
def is_eq_mode():
    """
    Check whether the mount is in equatorial mode.

    Returns ``True`` when the Seestar has been parked with the
    equatorial wedge enabled (i.e. ``scope_park(equ_mode=True)``).

    Returns
    -------
    bool

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.is_eq_mode()
        True

    """
    return get_mount_state().get("equ_mode")


@multiple_ips
def is_tracking():
    """
    Check whether the mount is currently sidereal-tracking.

    Returns
    -------
    bool

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.is_tracking()
        False

    """
    return get_mount_state().get("tracking")


@multiple_ips
def is_parked():
    """
    Check whether the Seestar arm is in the closed (parked) position.

    Returns
    -------
    bool

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.is_parked()
        True

    """
    return get_mount_state().get("close")


@multiple_ips
def get_coords():
    """
    Get the mount's current equatorial and horizontal coordinates.

    Queries both the RA/Dec and Alt/Az endpoints and merges the results
    into a single dictionary.

    Returns
    -------
    dict
        Dictionary with keys:

        - ``'ra'`` (float) — Right Ascension in decimal hours.
        - ``'dec'`` (float) — Declination in decimal degrees.
        - ``'alt'`` (float) — Altitude in decimal degrees.
        - ``'az'`` (float) — Azimuth in decimal degrees.

    Raises
    ------
    ValueError
        If either coordinate endpoint returns an error (e.g. the mount
        has not been initialised).

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_coords()
        {'ra': 13.398, 'dec': 54.925, 'alt': 42.3, 'az': 312.7}

    """
    eq_dict = raw.scope_get_equ_coord()
    altaz_dict = raw.scope_get_horiz_coord()

    # Tolerate both firmware return shapes: newer firmware returns
    # scope_get_equ_coord as {"ra":.., "dec":..}, older as [ra, dec].
    ra, dec = _pair(eq_dict, ("ra", "dec"))
    alt, az = _pair(altaz_dict, ("alt", "az"))

    if all(isinstance(v, (int, float)) and not isinstance(v, bool)
           for v in (ra, dec, alt, az)):
        return {"ra": ra, "dec": dec, "alt": alt, "az": az}
    else:
        raise ValueError(f"Could not get coordinates: {eq_dict}, {altaz_dict}")


@multiple_ips
def get_exposure(which="stack_l"):
    """
    Get the current exposure time in milliseconds.

    The Seestar maintains two independent exposure settings:
    ``'stack_l'`` for long-exposure stacking, and ``'continuous'`` for
    the live-view / continuous-exposure mode.

    Parameters
    ----------
    which : str, optional
        Which exposure to query.  One of ``'stack_l'`` (default) or
        ``'continuous'``.

    Returns
    -------
    int
        Exposure time in milliseconds.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_exposure()           # Stacking exposure
        10000
        >>> status.get_exposure("continuous")   # Live-view exposure
        500

    """
    params = {"method": "get_setting", "params": {"keys": ["exp_ms"]}}
    payload = send_command(params)
    return payload["result"]["exp_ms"][which]


@multiple_ips
def get_filter():
    """
    Get the current filter-wheel position.

    The Seestar S50 filter wheel has three positions:

    - **0** — Dark (shutter closed).
    - **1** — IR-cut (open, 400–700 nm with Bayer matrix).
    - **2** — Narrow-band / light-pollution (30 nm OIII + 20 nm Ha).

    Returns
    -------
    dict
        Response dictionary whose ``'result'`` key contains the
        integer position.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_filter()
        {'jsonrpc': '2.0', ..., 'result': 1, 'code': 0, 'id': 1}

    """
    params = {"method": "get_wheel_position"}
    return send_command(params)


@multiple_ips
def get_target_name():
    """
    Get the target name from the current observation sequence setting.

    This returns the group name that was set when the observation
    sequence was configured (e.g. via ``raw.set_sequence_setting``).

    Returns
    -------
    str or None
        The group name (e.g. ``"M 81"``), or ``None`` if no sequence
        is configured.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_target_name()
        'M 81'

    """
    params = {"method": "get_sequence_setting"}
    return send_command(params).get("group_name")


@multiple_ips
def get_target_name2():
    """
    Get the target name from the image-name field.

    This is an alternative to :func:`get_target_name` that reads the
    name embedded in the image filename template rather than the
    sequence setting.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_target_name2()

    """
    params = {"method": "get_img_name_field"}
    return send_command(params)


def azimuth_to_compass(degrees):
    """
    Convert an azimuth angle to a 16-point compass direction.

    Uses the standard meteorological convention where 0° is North,
    90° is East, 180° is South, and 270° is West.

    Parameters
    ----------
    degrees : float
        Azimuth in decimal degrees [0, 360).

    Returns
    -------
    str
        One of the 16 compass points: ``'N'``, ``'NNE'``, ``'NE'``,
        ``'ENE'``, ``'E'``, ``'ESE'``, ``'SE'``, ``'SSE'``, ``'S'``,
        ``'SSW'``, ``'SW'``, ``'WSW'``, ``'W'``, ``'WNW'``, ``'NW'``,
        ``'NNW'``.

    Examples
    --------

        >>> from seestarpy.status import azimuth_to_compass
        >>> azimuth_to_compass(0)
        'N'
        >>> azimuth_to_compass(135)
        'SE'
        >>> azimuth_to_compass(312.7)
        'NW'

    """
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW"
    ]
    idx = int((degrees % 360) / 22.5 + 0.5) % 16
    return directions[idx]