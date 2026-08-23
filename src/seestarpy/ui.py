import threading

from . import raw
from . import connection as conn
from .connection import multiple_ips
from .plan import resolve_name
from .status import get_filter, is_eq_mode, pixel_scale


@multiple_ips
def open():
    """
    Open the Seestar arm by moving it to the horizontal position.

    This must be called before slewing to a target. You cannot goto an
    object directly from the parked position.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.open()
        >>> ssp.open(ips="all")     # Open all connected Seestars

    """
    return raw.scope_move_to_horizon()


@multiple_ips
def close(eq_mode=None):
    """
    Close the Seestar arm and set the mode to EQ or AzAlt.

    Parameters
    ----------
    eq_mode : bool or None, optional
        - ``True`` : explicitly set EQ mode.
        - ``False`` : explicitly set AzAlt mode.
        - ``None`` : use the current mode. Default is ``None``.

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------
    ::

        >>> import seestarpy as ssp
        >>> ssp.close()             # Use the current value for EQ mode
        >>> ssp.close(False)        # Explicitly set the mount mode to AzAlt

    """
    eq_mode = is_eq_mode() if eq_mode is None else eq_mode
    return raw.scope_park(eq_mode)


@multiple_ips
def goto(ra_dec=()):
    """
    Move the scope arm to a given position.

    Accepts an ``(ra, dec)`` tuple, or the strings ``'park'`` /
    ``'horizon'`` as shortcuts.

    Parameters
    ----------
    ra_dec : tuple of float, or str
        - ``(ra, dec)`` : decimal hour angle [0, 24] and declination
          [-90, 90].
        - ``'park'`` : park the scope.
        - ``'horizon'`` : move to the horizontal position.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.goto((13.4, 54.8))          # Mizar
        >>> ssp.goto((5.63, -69.4))         # Tarantula Nebula
        >>> ssp.goto("park")
        >>> ssp.goto("horizon")

    """
    if isinstance(ra_dec, (tuple, list)) and len(ra_dec) == 2:
        return raw.scope_goto(*ra_dec)
    elif isinstance(ra_dec, str):
        if ra_dec.lower() == "park":
            return raw.scope_park()
        elif ra_dec.lower() == "horizon":
            return raw.scope_move_to_horizon()
    else:
        raise ValueError(
            f"ra_dec must be one of: [(ra, dec), 'park', 'horizon']: {ra_dec}")


@multiple_ips
def tracking(flag=None):
    """
    Get or set the mount tracking state.

    Parameters
    ----------
    flag : bool or None, optional
        - ``None`` : return the current tracking state.
        - ``True`` / ``False`` : enable or disable tracking.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------
    ::

        >>> import seestarpy as ssp
        >>> ssp.tracking()
        False
        >>> ssp.tracking(False)     # Turn off tracking

    """
    if flag is None:
        return raw.scope_get_track_state()
    elif isinstance(flag, bool):
        return raw.scope_set_track_state(flag)
    else:
        raise ValueError(f"flag must be one of: [None, True, False]: {flag}")


@multiple_ips
def exposure(exptime: int | None = None, which="stack_l"):
    """
    Get or set the exposure time.

    Parameters
    ----------
    exptime : int or None, optional
        - ``None`` : return the current exposure time.
        - ``int`` : set the exposure time in seconds (or milliseconds if > 100).
          Accepted values: 2, 5, 10, 20, 30, 60.
    which : str, optional
        Which exposure to set. One of ``'stack_l'`` or ``'continuous'``.
        Default is ``'stack_l'``.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------
    ::

        >>> import seestarpy as ssp
        >>> ssp.exposure()
        {'stack_l': 10000, 'continuous': 500}
        >>> ssp.exposure(exptime=30, which="stack_l")       # 30s exposure time
        {'Event': 'Setting', 'Timestamp': '1380808.244289322', 'wide_cam': False, 'exp_ms': {'stack_l': 30000}}
        >>> ssp.conn.find_available_ips(n_ip=3)
        >>> ssp.exposure(exptime=5, ips="all")               # 5s exposure time for all 3 connected Seestars

    """
    if exptime is None:
        return raw.get_setting().get("result", {}).get("exp_ms")

    exptime = int(exptime) // 1000 if exptime > 100 else int(exptime)
    if isinstance(exptime, int) and exptime in [2, 5, 10, 20, 30, 60]:
        return raw.set_setting(expert_mode=True, exp_ms={which: exptime * 1000})
    else:
        raise ValueError(f"exptime must be one of [None, int]: {exptime}")


#: Per-sub overhead (readout + save) in seconds, used to convert a dither
#: interval given in seconds into a whole number of sub-exposures.
SUB_OVERHEAD_S = 1.5


@multiple_ips
def dither(enabled: bool | None = None,
           radius_arcmin: float | None = None,
           every_n_subs: int | None = None,
           interval_s: float | None = None):
    """
    Get or set the dither pattern used while stacking.

    Dithering nudges the mount by a small random offset every few
    sub-exposures.  This matters for deep stacks: on an equatorially
    tracked field every sub lands on the *same* pixels, so flat-field and
    dark residuals add coherently and stop averaging down.  Dithering
    sweeps the field across the detector and breaks that up.  Alt-azimuth
    mounts get the same effect for free from field rotation.

    The firmware stores the throw in *pixels*; this function takes and
    reports it in *arcminutes*, converting with :func:`pixel_scale`.

    Parameters
    ----------
    enabled : bool or None, optional
        - ``None`` (and no other argument) : return the current settings.
        - ``bool`` : turn dithering on or off.
    radius_arcmin : float or None, optional
        Maximum offset from the field centre, in arcminutes.  2--3' is a
        good default: a few tens of pixels already averages over
        pixel-scale flat error, while a large radius shrinks the area
        common to every sub.  Large-scale vignetting cannot be dithered
        away at any amplitude.
    every_n_subs : int or None, optional
        Dither once every this many sub-exposures.  Every 5--6 subs
        (~2 min at 20 s) is a good default; at longer intervals short
        stacks see only a single position and gain nothing.
    interval_s : float or None, optional
        Alternative to *every_n_subs*: the desired cadence in seconds,
        converted to a whole number of subs using the current stacking
        exposure time.  Mutually exclusive with *every_n_subs*.

    Returns
    -------
    dict
        The current settings when called with no arguments, otherwise the
        firmware's reply to the set.

    Notes
    -----
    Setting *radius_arcmin*, *every_n_subs* or *interval_s* without
    passing *enabled* turns dithering on, on the assumption that you are
    configuring it because you want it.  Pass ``enabled=False``
    explicitly to configure it but leave it off.

    Firmware ships with dithering **enabled** by default, so a run that
    is meant to be undithered must disable it explicitly.

    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------
    ::

        >>> import seestarpy as ssp
        >>> ssp.dither()
        {'enabled': True, 'radius_arcmin': 2.39, 'radius_px': 60, 'every_n_subs': 5}
        >>> ssp.dither(radius_arcmin=2.5, every_n_subs=5)   # enables it too
        >>> ssp.dither(radius_arcmin=3, interval_s=120)     # cadence in seconds
        >>> ssp.dither(False)                               # undithered control
        >>> ssp.dither(False, ips="all")                    # ...on every Seestar

    """
    setting = raw.get_setting().get("result", {}) or {}
    cur = setting.get("stack_dither") or {}
    scale = pixel_scale()

    if enabled is None and radius_arcmin is None \
            and every_n_subs is None and interval_s is None:
        px = cur.get("pix") or 0
        return {"enabled": cur.get("enable"),
                "radius_arcmin": round(px * scale / 60.0, 2),
                "radius_px": px,
                "every_n_subs": cur.get("interval")}

    if every_n_subs is not None and interval_s is not None:
        raise ValueError("pass either every_n_subs or interval_s, not both")

    new = {"pix": cur.get("pix", 50),
           "interval": cur.get("interval", 5),
           "enable": cur.get("enable", False)}

    if radius_arcmin is not None:
        px = int(round(float(radius_arcmin) * 60.0 / scale))
        if not 1 <= px <= 500:
            raise ValueError(
                f"radius_arcmin={radius_arcmin} is {px} px, outside [1, 500]"
            )
        new["pix"] = px

    if interval_s is not None:
        exp_ms = (setting.get("exp_ms") or {}).get("stack_l") or 10000
        every_n_subs = max(1, round(float(interval_s)
                                    / (exp_ms / 1000.0 + SUB_OVERHEAD_S)))

    if every_n_subs is not None:
        if int(every_n_subs) < 1:
            raise ValueError(f"every_n_subs must be >= 1: {every_n_subs}")
        new["interval"] = int(every_n_subs)

    # Configuring the pattern implies wanting it on, unless told otherwise.
    new["enable"] = bool(enabled) if enabled is not None else True

    return raw.set_setting(stack_dither=new)


@multiple_ips
def filter_wheel(pos: int | str | None = None):
    """
    Get or set the filter-wheel position.

    Parameters
    ----------
    pos : int, str, or None, optional
        - ``None`` : return the current filter-wheel position.
        - ``1`` or ``'open'`` / ``'ircut'`` : open (IR-cut) filter.
        - ``2`` or ``'narrow'`` / ``'lp'`` : narrow-band / light-pollution filter.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import filter_wheel
        >>> filter_wheel()
        1
        >>> filter_wheel("ircut")
        >>> filter_wheel(2)

    """
    if pos is None:
        return get_filter()

    if isinstance(pos, int) and pos in [1, 2]:
        pos_i = pos
    elif isinstance(pos, str) and pos.lower() in ["open", "narrow"]:
        pos_i = {"open": 1, "ircut": 1, "narrow": 2, "lp": 2}[pos.lower()]
    else:
        raise ValueError(f"Invalid filter wheel value: {pos}")
    return raw.set_wheel_position(pos_i)


@multiple_ips
def focuser(pos: int | str | None = None):
    """
    Get or set the focuser position.

    Parameters
    ----------
    pos : int, str, or None, optional
        - ``None`` : return the current focuser position.
        - ``int`` : move the focuser to this position.
        - ``'auto'`` : start the auto-focus routine.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> from seestarpy import focuser
        >>> focuser()
        1580
        >>> focuser("auto")
        >>> focuser(pos=1605)

    """
    if pos is None:
        return raw.get_focuser_position()
    elif isinstance(pos, int):
        return raw.move_focuser(pos)
    elif isinstance(pos, str) and pos.lower() =="auto":
        return raw.start_auto_focuse()
    else:
        raise ValueError(f"pos must be one of [None, int, 'auto']: {pos}")


@multiple_ips
def goto_target(target_name, ra=None, dec=None, lp_filter=False):
    """
    Slew to a target by name and coordinates, then start viewing.

    This triggers an ``AutoGoto`` sequence: the telescope slews to the
    given coordinates, runs a plate-solve loop, and then enters
    ``ContinuousExposure`` mode.

    If *ra* and *dec* are omitted, the coordinates are resolved
    automatically from *target_name* using the CDS Sesame name resolver
    (SIMBAD/NED/VizieR).  This supports standard designations such as
    Messier (``"M42"``), NGC/IC, HD, HIP, Bayer names, etc.

    Parameters
    ----------
    target_name : str
        Name of the target (e.g. ``"M42"``, ``"NGC 884"``).  Also used
        as the directory name on the Seestar's internal storage.  When
        *ra* and *dec* are ``None``, this name is passed to
        :func:`~seestarpy.plan.resolve_name` to look up coordinates.
    ra : float or None, optional
        Right Ascension in decimal hours.  If ``None`` (default),
        resolved from *target_name*.
    dec : float or None, optional
        Declination in decimal degrees.  If ``None`` (default),
        resolved from *target_name*.
    lp_filter : bool, optional
        Use the light-pollution filter. Default is ``False``.

    Returns
    -------
    dict

    Raises
    ------
    LookupError
        If *ra*/*dec* are ``None`` and *target_name* cannot be resolved.
    ConnectionError
        If the CDS Sesame service is unreachable.
    ValueError
        If only one of *ra*/*dec* is provided.

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.goto_target("M42")                                # name resolved
        >>> ssp.goto_target("M8", lp_filter=True)                 # name + LP filter
        >>> ssp.goto_target("Mizar", ra=13.4, dec=54.9)           # explicit coords
        >>> ssp.goto_target("M31", ips="all")                     # all Seestars

    """
    if ra is None and dec is None:
        ra, dec = resolve_name(target_name)
    elif ra is None or dec is None:
        raise ValueError(
            "Provide both ra and dec, or omit both to resolve from target_name."
        )
    return raw.iscope_start_view(ra, dec, target_name, lp_filter)


@multiple_ips
def stop_view():
    """
    Stop the current viewing session.

    Sets the camera mode to ``'none'`` and stops all activity.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.stop_view()
        >>> ssp.stop_view(ips="all")    # Stop all connected Seestars

    """
    return raw.iscope_stop_view()


@multiple_ips
def start_stack(restart=True):
    """
    Start stacking sub-frames on the current target.

    Parameters
    ----------
    restart : bool, optional
        Restart the stacking sequence from scratch. Default is ``True``.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.goto_target("M31")
        >>> ssp.start_stack()
        >>> ssp.start_stack(ips="all")  # Start stacking on all Seestars

    """
    return raw.iscope_start_stack(restart)


@multiple_ips
def set_eq_mode(equ_mode=True):
    """
    Park the scope and set the equatorial mode.

    Parameters
    ----------
    equ_mode : bool, optional
        Enable equatorial mode. Default is ``True``.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.open()
        >>> ssp.set_eq_mode(True)       # Park into EQ mode
        >>> ssp.set_eq_mode(False)      # Park into AzAlt mode

    """
    return raw.scope_park(equ_mode)


#: 3PPA ``state_code`` values, as emitted in the firmware's ``3PPA`` event.
PA_STATE_CODES = {
    1: "start",
    5: "move1",
    6: "delay1",
    10: "move2",
    11: "delay2",
    14: "calc3",
    17: "calc4",
}


def _pa_progress(frame):
    """Render one polar-alignment event as a short progress line, or ``None``.

    Only the events that say something about progress are rendered; the
    firmware also interleaves ``PiStatus``, ``Exposure`` and friends, which
    are noise here.
    """
    ev = frame.get("Event")
    state = frame.get("state")

    if ev == "3PPA":
        code = frame.get("state_code")
        name = PA_STATE_CODES.get(code, state)
        line = f"  3PPA      {name} (state_code={code})"
        err = frame.get("pa_error")
        if err:
            line += (f"\n            error: {err['total']:.4f} deg"
                     f"  az={err['x']:+.4f}  alt={err['y']:+.4f}"
                     f"  ({err['total_arcsec']:.0f}\")")
        return line

    if ev == "PlateSolve":
        if frame.get("page"):               # per-frame chatter, skip
            return None
        if state == "working":
            return "  solving   ..."
        if state == "complete":
            ra, dec = frame.get("ra_dec", (None, None))
            return f"  solved    ra={ra:.4f}h dec={dec:.4f}deg"
        return f"  solving   {state}"

    if ev == "ScopeGoto":
        if state == "working":
            return "  slewing   to the first alignment point"
        if state == "complete":
            return f"  slewed    ({frame.get('lapse_ms', 0) / 1000:.1f} s)"
        return (f"  slewing   {state}: {frame.get('error')} "
                f"(code {frame.get('code')})")

    if ev == "MoveByAngle" and state in ("start", "complete"):
        return "  rotating  RA axis" if state == "start" else "  rotated"

    if ev == "EqModePA" and state in ("complete", "fail", "cancel"):
        if state == "complete":
            return (f"  RESULT    {frame['total']:.4f} deg  "
                    f"az={frame['x']:+.4f}  alt={frame['y']:+.4f}")
        return f"  {state.upper()}"

    return None


@multiple_ips
def polar_align(dec_pos_index=3, restart=True, verbose=True, timeout=300):
    """
    Run a three-point polar alignment (3PPA) and block until it finishes.

    The scope must already be in EQ mode.  Starting from the EQ-parked
    position works (the firmware slews to the first point itself, which
    takes ~45 s); starting from an already-deployed position is quicker.

    The firmware ties the alignment to the TCP connection that started it
    and drops an idle socket after ~15.5 s — so an unattended
    :func:`~seestarpy.raw.start_polar_align` is cancelled roughly 19 s in,
    leaving the mount stopped mid-slew.  This wrapper holds the connection
    open for the whole run (see :class:`~seestarpy.connection.keepalive`),
    which is what lets the alignment actually complete.

    Parameters
    ----------
    dec_pos_index : int, optional
        Which DEC band to align on, as offered by the app's pitch picker.
        Default ``3``.  Roughly ``dec = 30 * index - 43`` degrees, so
        ``2`` -> ~17 deg, ``3`` -> ~47 deg, ``4`` -> ~77 deg.  Pick one
        that is clear of obstructions.
    restart : bool, optional
        ``True`` (default) runs the full three-point sequence.  ``False``
        re-measures at the current position without moving the DEC arm —
        use it to check the residual after physically adjusting the
        tripod.
    verbose : bool, optional
        Print a progress line per alignment event.  Default ``True``.
    timeout : float, optional
        Seconds to wait for the alignment to finish.  Default ``300``.

    Returns
    -------
    dict
        ``{'state': 'complete'|'fail'|'cancel'|'timeout', 'total': float,
        'x': float, 'y': float, 'lapse_ms': int}``.  ``total`` is the
        polar-axis error in degrees; ``x`` is the azimuth component and
        ``y`` the altitude component — both are how far the *mount* is
        off, so correct the tripod by the same amount in the opposite
        direction.  Values are ``None`` unless the state is ``complete``.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.

    Examples
    --------
    ::

        >>> import seestarpy as ssp
        >>> ssp.set_eq_mode(True)               # park into EQ mode
        >>> res = ssp.polar_align()
        >>> res['total']                        # degrees off the pole
        0.9209
        >>> ssp.polar_align(restart=False)      # re-check after adjusting

    """
    done = threading.Event()
    result = {"state": None, "total": None, "x": None, "y": None,
              "lapse_ms": None}

    def on_event(frame):
        if frame.get("Event") not in ("3PPA", "PlateSolve", "ScopeGoto",
                                      "MoveByAngle", "EqModePA"):
            return
        if verbose:
            line = _pa_progress(frame)
            if line:
                print(line, flush=True)
        if frame.get("Event") == "EqModePA":
            state = frame.get("state")
            if state in ("complete", "fail", "cancel"):
                result.update(
                    state=state,
                    total=frame.get("total"),
                    x=frame.get("x"),
                    y=frame.get("y"),
                    lapse_ms=frame.get("lapse_ms"),
                )
                done.set()

    if verbose:
        what = (f"restart, dec_pos_index={dec_pos_index}" if restart
                else "re-measure at current position")
        print(f"Polar alignment on {conn.current_ip()} ({what})", flush=True)

    with conn.keepalive(on_event=on_event):
        raw.start_polar_align(restart=restart, dec_pos_index=dec_pos_index)
        if not done.wait(timeout):
            result["state"] = "timeout"
            if verbose:
                print(f"  TIMEOUT   after {timeout:.0f} s", flush=True)

    return result
