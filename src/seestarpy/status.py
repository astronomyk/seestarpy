from datetime import datetime as dt

from . import raw
from .connection import current_ip, multiple_ips


#: Sensor pixel pitch in microns (IMX462, used by the S50 and S30 Pro).
PIXEL_SIZE_UM = 2.9

#: Plate scale in arcsec/pixel used if the focal length can't be read back.
#: 206.265 * 2.9 / 250 mm = 2.39 "/px for the S50 telephoto.
DEFAULT_PIXEL_SCALE = 2.39


def pixel_scale(focal_mm=None):
    """
    Return the plate scale in arcsec per pixel for the connected Seestar.

    Derived from the focal length reported by the device, so it stays
    correct for the S30 Pro's wide camera (160 mm, 3.74 "/px) as well as
    the S50 telephoto (250 mm, 2.39 "/px).  Falls back to
    :data:`DEFAULT_PIXEL_SCALE` if the device can't be read.

    Parameters
    ----------
    focal_mm : float or None, optional
        Focal length in mm.  If ``None`` (default) it is queried from the
        device.  Pass it explicitly to save a round-trip when you have
        already fetched the device block.

    Returns
    -------
    float
        Plate scale in arcsec/pixel.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.pixel_scale()
        2.3926...

    """
    if focal_mm is None:
        try:
            device = raw.get_device_state(keys=["device"])["result"]["device"]
            focal_mm = device.get("focal_len")
        except Exception:
            focal_mm = None
    try:
        focal_mm = float(focal_mm or 0)
    except (TypeError, ValueError):
        focal_mm = 0
    if focal_mm > 0:
        return 206.265 * PIXEL_SIZE_UM / focal_mm
    return DEFAULT_PIXEL_SCALE


def as_number(value):
    """Return *value* if it is a real number, otherwise ``None``.

    The firmware answers an unsupported query with a string or an error dict
    where a number is expected, so arithmetic on a reply field is never safe
    without this.  ``bool`` is deliberately excluded: ``True`` is an ``int``
    in Python, but a flag is not a measurement.

    This is the one numeric coercion in the package —
    :mod:`seestarpy.dashboard.monitor` imports it rather than keeping its own.

    Examples
    --------
    ::

        >>> as_number(42), as_number("---"), as_number(True), as_number(None)
        (42, None, None, None)

    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def coord_pair(result, keys):
    """Pull a coordinate pair out of an RPC *result* of either shape.

    The firmware return shape is **version dependent**:
    ``scope_get_equ_coord`` answers with a dict (``{"ra": .., "dec": ..}``)
    while ``scope_get_horiz_coord`` answers with a bare ``[alt, az]`` list,
    and which you get has changed between versions.  Non-numeric or missing
    values become ``None``.

    Parameters
    ----------
    result : dict or list
        The ``result`` field of the reply, already unwrapped.
    keys : tuple of str
        Keys to read for the (first, second) element when *result* is a dict,
        e.g. ``("ra", "dec")`` or ``("alt", "az")``.

    Returns
    -------
    tuple
        ``(first, second)``, each a number or ``None``.
    """
    if isinstance(result, dict):
        return as_number(result.get(keys[0])), as_number(result.get(keys[1]))
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        return as_number(result[0]), as_number(result[1])
    return None, None


def _num(val, nd=None):
    """Round *val* for display, or return ``"---"`` if it isn't a number.

    The display counterpart to :func:`as_number`: ``status_bar`` fills its
    cells from live queries, and an endpoint that errored yields a string
    where a number belongs, which ``round()`` would choke on.
    """
    val = as_number(val)
    if val is None:
        return "---"
    return round(val, nd) if nd is not None else round(val)


def _pair(resp, keys):
    """Unwrap an RPC envelope and delegate to :func:`coord_pair`.

    Tolerates error responses, which have no ``result``.
    """
    result = resp.get("result") if isinstance(resp, dict) else None
    return coord_pair(result, keys)


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
        string; ``"dict"`` returns the same values unformatted, which is
        what you want for logging a run rather than reading it.

    Returns
    -------
    str or dict
        The formatted status table, or a dictionary of every value in it.
        In the dictionary a field the firmware did not report is ``None``
        rather than the table's ``"---"`` placeholder, and numbers are
        unrounded.  The table is rendered *from* this dictionary, so the
        two can never disagree.

    Raises
    ------
    ValueError
        If *return_type* is neither ``"str"`` nor ``"dict"``.

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
        | STAGE          | ARCSEC / PIX   | DITHER         | GAIN           | FIRMWARE |
        |================|================|================|================|==========|

    Examples
    --------

        >>> from seestarpy import status
        >>> print(status.status_bar())

    Log a night to CSV instead of reading it::

        >>> row = status.status_bar(return_type="dict")
        >>> row["stacked_frames"], row["dropped_frames"], row["gain"]
        (204, 6, 80)

    """

    dev = raw.get_device_state(["balance_sensor", "mount", "pi_status",
                            "storage", "setting", "device"]).get("result", {})
    app = raw.iscope_get_app_state().get("result", {})
    view = app.get("View", {})
    azalt = _pair(raw.scope_get_horiz_coord(), ("alt", "az"))
    # ``scope_get_equ_coord`` is the command-socket (port 4700) RA/Dec method
    # the official app uses on all firmware.  ``scope_get_ra_dec`` is
    # primarily the port-4800 heartbeat and answers with a three-element
    # list, which is what used to crash this dashboard -- not a rejection.
    # This endpoint returns a dict on newer firmware and a bare list on
    # older; _pair() normalises both.
    radec = _pair(raw.scope_get_equ_coord(), ("ra", "dec"))

    mount = dev.get("mount", {})
    setting = dev.get("setting", {})
    device = dev.get("device", {})
    stack = view.get("Stack", {})
    # ``PlateSolve`` moved between the app-state root and the View block
    # across firmware versions; accept either.
    solve = app.get("PlateSolve",
                    view.get("PlateSolve", {}).get("PlateSolve", {}))
    target_ra_dec = view.get("target_ra_dec") or [None, None]
    scale = pixel_scale(device.get("focal_len"))
    dith = setting.get("stack_dither") or {}

    # The live gain lives on the View block; ``isp_gain`` is a sentinel
    # (-9990.0) unless manual exposure is in use, so only trust it if sane.
    gain = view.get("gain")
    if gain is None:
        isp = setting.get("isp_gain")
        gain = isp if isinstance(isp, (int, float)) and isp >= 0 else None

    exp_ms = stack.get("Exposure", {}).get("exp_ms")

    # Every cell of the table, as the value the firmware actually gave --
    # ``None`` where it gave nothing.  The table below is rendered from
    # these, so the two return types can never disagree.
    values = {
        "mode": view.get("mode"),
        "state": view.get("state"),
        "error": view.get("error"),
        "target_name": view.get("target_name"),
        "stage": view.get("stage"),

        "target_ra": target_ra_dec[0],
        "target_dec": target_ra_dec[1],
        "ra": radec[0] if isinstance(radec[0], (int, float)) else None,
        "dec": radec[1] if isinstance(radec[1], (int, float)) else None,
        "alt": azalt[0] if isinstance(azalt[0], (int, float)) else None,
        "az": azalt[1] if isinstance(azalt[1], (int, float)) else None,
        "balance_angle": dev.get("balance_sensor", {}).get("data", {}).get("angle"),
        "pixel_scale": scale,

        "lp_filter": view.get("lp_filter"),
        "exp_ms": exp_ms,
        "stacked_frames": stack.get("stacked_frame"),
        "dropped_frames": stack.get("dropped_frame"),
        "tracking": mount.get("tracking"),
        "dither_enabled": dith.get("enable"),
        "dither_pix": dith.get("pix"),
        "dither_interval": dith.get("interval"),
        "gain": gain,

        "dark_frame_percent": app.get("DarkLibrary", {}).get("percent"),
        "focus_position": app.get("FocuserMove", {}).get("position"),
        "plate_solve_state": solve.get("state"),
        "plate_solve_error": solve.get("error"),

        "battery_percent": dev.get("pi_status", {}).get("battery_capacity"),
        "free_mb": dev.get("storage", {}).get("storage_volume", [{}])[0].get("free_mb"),
        "equ_mode": mount.get("equ_mode"),
        "firmware": device.get("firmware_ver_string"),
        "timestamp": dt.now().isoformat(timespec="seconds"),
    }

    # Derived, display-only: arcminutes of dither throw, and the compass point.
    values["dither_arcmin"] = (
        round(dith["pix"] * scale / 60.0, 2)
        if dith.get("enable") and isinstance(dith.get("pix"), (int, float))
        else None
    )
    values["compass"] = (azimuth_to_compass(values["az"])
                         if values["az"] is not None else None)

    if return_type == "dict":
        return values
    if return_type != "str":
        raise ValueError(
            f"return_type must be 'str' or 'dict', not {return_type!r}"
        )

    def _cell(key, nd=None):
        """The value for *key*, rounded for display, or ``---``."""
        return _num(values[key], nd) if values[key] is not None else "---"

    t11 = f'{values["mode"] or "---":^14}'
    t12 = f'{values["state"] or "---":^14}'
    t13 = f'{values["error"] or "---":^14}'
    # Target names are user-set and can be longer than the cell, which would
    # push the whole table out of alignment -- truncate rather than overflow.
    target_name = str(values["target_name"] or "---")
    if len(target_name) > 14:
        target_name = target_name[:13] + "…"
    t14 = f'{target_name:^14}'

    t21a = f'{_cell("target_ra", 3):<7}'
    t21b = f'{_cell("target_dec", 2):<6}'
    t22a = f'{_cell("ra", 3):<7}'
    t22b = f'{_cell("dec", 2):<6}'
    al = f'{_cell("alt"):<4}'
    az = f'{_cell("az"):<4}'
    co = f'{(values["compass"] or "---"):<4}'
    t24 = f'{_cell("balance_angle", 3):^14}'

    t31 = f'{str(values["lp_filter"]):^14}'
    t32 = f'{(exp_ms or 0)/1000:^14}'
    t33a = f'{values["stacked_frames"] if values["stacked_frames"] is not None else "---":<6}'
    t33b = f'{values["dropped_frames"] if values["dropped_frames"] is not None else "---":<6}'
    t34 = f'{str(values["tracking"]):^14}'

    t41 = f'{values["dark_frame_percent"] if values["dark_frame_percent"] is not None else "---":^14}'
    t42 = f'{values["focus_position"] if values["focus_position"] is not None else "---":^14}'
    t43 = f'{values["plate_solve_state"] or "---":^14}'
    t44 = f'{values["plate_solve_error"] or "---":^14}'

    # ^8 to match the other cells in this column -- at ^7 the BATTERY row
    # rendered one character short and the table came out ragged.
    t51 = f'{str(values["battery_percent"])+"%":^8}'
    t52 = f'{values["free_mb"] if values["free_mb"] is not None else "---":^8}'
    t53 = f'{str(values["equ_mode"]):^8}'
    t54 = f'{dt.now().strftime("%H:%M:%S"):^8}'

    # Fifth row.  DITHER is shown because an undithered run and a dithered
    # one are otherwise indistinguishable at a glance, and the firmware
    # ships with dithering ON by default.
    if values["dither_arcmin"] is not None:
        dither_txt = f"{values['dither_arcmin']:.1f}' /{dith.get('interval', '?')} sub"
    else:
        dither_txt = "off" if dith else "---"
    t61 = f'{values["stage"] or "---":^14}'
    t62 = f'{_cell("pixel_scale", 2):^14}'
    t63 = f'{dither_txt:^14}'
    t64 = f'{values["gain"] if values["gain"] is not None else "---":^14}'
    t65 = f'{str(values["firmware"] or "---"):^8}'

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
|----------------|----------------|----------------|----------------|----------|
|     STAGE      |  ARCSEC / PIX  |     DITHER     |      GAIN      | FIRMWARE |
| {t61         } | {t62         } | {t63         } | {t64         } | {t65   } |
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

    See Also
    --------
    firmware_version : both forms at once, cached per scope.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_firmware_version()
        '7.18'

    """
    return firmware_version()[0]


#: ``{ip: (version_string, version_int)}``, filled by :func:`firmware_version`.
_firmware_cache = {}


def firmware_version(ip=None, refresh=False):
    """Return ``(version_string, version_int)`` for one Seestar, cached.

    Firmware gates behaviour in more and more places — the batch stacker's
    sub-frame path format at 7.75, the ``preview`` transport block at 8.46 —
    so this is the seam those checks share.  Both forms are returned because
    both are wanted: the string to show a human, the int to compare.

    Cached per address, since firmware cannot change while the scope is up,
    and a stacking loop should not re-query it for every block.

    Parameters
    ----------
    ip : str or None, optional
        Which Seestar.  Defaults to
        :func:`~seestarpy.connection.current_ip`, so this respects an
        enclosing ``ips=`` broadcast.
    refresh : bool, optional
        Re-query even if the address is already cached — after a firmware
        update, say.  Default ``False``.

    Returns
    -------
    tuple
        ``(str, int)``, e.g. ``("8.46", 2846)``.  Either element is ``None``
        if the device could not be read.

    Examples
    --------
    ::

        >>> from seestarpy import status
        >>> status.firmware_version()
        ('8.46', 2846)
        >>> ver_string, ver_int = status.firmware_version()
        >>> ver_int >= 2846        # does this scope have the preview block?
        True

    """
    ip = ip or current_ip()
    if refresh or ip not in _firmware_cache:
        try:
            device = raw.get_device_state(["device"])["result"]["device"]
            _firmware_cache[ip] = (device.get("firmware_ver_string"),
                                   as_number(device.get("firmware_ver_int")))
        except Exception:
            # Don't cache a failure: a scope that was mid-boot should be
            # retried, not written off for the rest of the session.
            return (None, None)
    return _firmware_cache[ip]


@multiple_ips
def get_serial_number():
    """
    Get the Seestar serial number.

    Also available under the shorthand alias :func:`get_sn`.

    Returns
    -------
    str
        Serial number, e.g. ``"a3497936"``.

    Notes
    -----
    Accepts the ``ips`` keyword for querying multiple Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import status
        >>> status.get_serial_number()
        'a3497936'
        >>> status.get_sn(ips="all")
        {'192.168.1.81': 'a3497936', '192.168.1.78': 'ce545589'}

    """
    return (raw.get_device_state(["device"])
            .get("result", {})
            .get("device", {})
            .get("sn"))


#: Shorthand alias for :func:`get_serial_number`.
get_sn = get_serial_number


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
    return raw.get_setting()["result"]["exp_ms"][which]


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
    return raw.get_wheel_position()


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
    # ``group_name`` lives inside the JSON-RPC ``result``, not on the
    # envelope -- reading it off the top level made this return None always.
    resp = raw.get_sequence_setting()
    return (resp.get("result") or {}).get("group_name")


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