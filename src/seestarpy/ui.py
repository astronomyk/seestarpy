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
def goto(ra_dec=(), verbose=True, timeout=180):
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
    verbose : bool, optional
        Print a progress line per event. Default ``True``.
    timeout : float, optional
        Seconds to wait for the move to finish. Default ``180``.

    Returns
    -------
    dict
        ``{'state', 'lapse_ms', 'cur_ra_dec', 'dist_deg', 'error', 'code'}``.
        ``state`` is ``'complete'``, ``'fail'``, ``'cancel'`` or
        ``'timeout'``; ``dist_deg`` is how far off the target the mount
        finished, when the firmware reports it.

    Notes
    -----
    Accepts the ``ips`` keyword for sending the command to multiple
    Seestars simultaneously.

    This **blocks** until the mount reports the move finished, rather than
    returning as soon as the command is accepted.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.goto((13.4, 54.8))          # Mizar
        >>> ssp.goto((5.63, -69.4))         # Tarantula Nebula
        >>> ssp.goto("park")
        >>> ssp.goto("horizon")
        >>> ssp.goto((13.4, 54.8), verbose=False)

    """
    if isinstance(ra_dec, (tuple, list)) and len(ra_dec) == 2:
        ra, dec = ra_dec
        start = lambda: raw.scope_goto(ra, dec)
        terminal = "ScopeGoto"
        header = f"Goto ra={ra} dec={dec} on {conn.current_ip()}"
    elif isinstance(ra_dec, str) and ra_dec.lower() == "park":
        start, terminal = raw.scope_park, "ScopeHome"
        header = f"Park on {conn.current_ip()}"
    elif isinstance(ra_dec, str) and ra_dec.lower() == "horizon":
        start, terminal = raw.scope_move_to_horizon, "ScopeMoveToHorizon"
        header = f"Open to horizon on {conn.current_ip()}"
    else:
        # An unrecognised string must raise, not return None and look like a
        # successful no-op.
        raise ValueError(
            f"ra_dec must be one of: [(ra, dec), 'park', 'horizon']: "
            f"{ra_dec!r}")

    return _await_operation(
        start=start,
        terminal=terminal,
        watch={terminal, "ScopeTrack", "Alert"},
        extract=lambda f: {"lapse_ms": f.get("lapse_ms"),
                           "cur_ra_dec": f.get("cur_ra_dec"),
                           "dist_deg": f.get("dist_deg"),
                           "error": f.get("error"), "code": f.get("code")},
        verbose=verbose,
        timeout=timeout,
        header=header,
    )


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

    names = {"open": 1, "ircut": 1, "narrow": 2, "lp": 2}
    if isinstance(pos, int) and pos in [1, 2]:
        pos_i = pos
    elif isinstance(pos, str) and pos.lower() in names:
        pos_i = names[pos.lower()]
    else:
        raise ValueError(
            f"Invalid filter wheel value: {pos!r}. "
            f"Use 1 or 2, or one of {sorted(names)}."
        )
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
def goto_target(target_name, ra=None, dec=None, lp_filter=False,
                verbose=True, timeout=300):
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

    result = _await_operation(
        start=lambda: raw.iscope_start_view(ra, dec, target_name, lp_filter),
        terminal="AutoGoto",
        watch={"AutoGoto", "AutoGotoStep", "ScopeGoto", "PlateSolve",
               "ScopeTrack", "Alert"},
        extract=lambda f: {"lapse_ms": f.get("lapse_ms"),
                           "count": f.get("count"),
                           "error": f.get("error"), "code": f.get("code")},
        verbose=verbose,
        timeout=timeout,
        header=f"Goto {target_name} (ra={ra:.5f}, dec={dec:.5f}) on "
               f"{conn.current_ip()}",
    )
    result.update(target_name=target_name, ra=ra, dec=dec)
    return result


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


#: Events that carry no progress information worth printing.
_QUIET_EVENTS = frozenset({
    "PiStatus", "Exposure", "ContinuousExposure", "Setting", "SelectCamera",
    "BalanceSensor", "GSensorMove", "Temp", "DiskSpace", "AIProcess",
    "get_device_state", "iscope_get_app_state", "scope_get_equ_coord",
    "scope_get_horiz_coord", "test_connection",
})

#: Terminal states a firmware operation can end in.
_TERMINAL_STATES = frozenset({"complete", "fail", "cancel"})


def _event_name(frame):
    """The event name, tolerating the ``Event``/``event`` key spelling."""
    return frame.get("Event") or frame.get("event")


def _is_outer(frame):
    """True if *frame* is an operation's own terminal event, not a sub-step.

    The firmware reports a finished operation twice: once as an inner
    per-page/per-step frame (carrying ``page``, or nothing but an error),
    and once as the operation's own frame carrying ``lapse_ms`` and/or
    ``route``.  Only the latter means the whole operation is over.  Checked
    against every terminal event in ``tests/event_output_20250722.dat``.
    """
    return "page" not in frame and ("route" in frame or "lapse_ms" in frame)


def _await_operation(start, terminal, watch, extract, verbose, timeout,
                     header=None):
    """Start a connection-bound operation and block until it finishes.

    The firmware ties operations like polar alignment, autofocus and goto to
    the TCP connection that issued them, and drops an idle socket after
    ~15.5 s — so the command is issued inside a
    :class:`~seestarpy.connection.keepalive`, which both holds the session
    open and pumps the events back to us.

    Parameters
    ----------
    start : callable
        Issues the RPC that begins the operation.
    terminal : str
        Event name whose terminal state ends the wait.
    watch : set of str
        Event names to render as progress.
    extract : callable
        Maps the terminal frame to the result fields for this operation.
    verbose, timeout : see the public wrappers.
    header : str or None
        Printed once before starting, when *verbose*.

    Returns
    -------
    dict
        ``extract``'s fields plus ``state`` (a terminal state, or
        ``'timeout'``).
    """
    done = threading.Event()
    # Seed every field this operation reports, so a caller can read them
    # unconditionally even when the run times out or fails.
    result = dict(extract({}), state=None)
    pending = {}
    last = [None, 0]        # last printed line, and how often it repeated

    def emit(line):
        """Print *line*, collapsing consecutive repeats into a xN counter.

        A retrying AutoGoto re-emits ``ScopeGoto working`` several times per
        attempt, which otherwise buries the useful lines in ``slewing ...``.
        """
        if line == last[0]:
            last[1] += 1
            print(f"{line}  (x{last[1] + 1})", flush=True)
            return
        last[0], last[1] = line, 0
        print(line, flush=True)

    def on_event(frame):
        ev = _event_name(frame)
        if ev in _QUIET_EVENTS or ev not in watch:
            return
        if verbose:
            line = _pa_progress(frame)
            if line:
                emit(line)
        if ev != terminal or frame.get("state") not in _TERMINAL_STATES:
            return
        payload = dict(extract(frame), state=frame.get("state"))
        if _is_outer(frame):
            result.update(payload)
            done.set()
        else:
            # An inner frame: remember it, but keep waiting for the
            # operation's own terminal event, which is authoritative.
            pending.update(payload)

    if verbose and header:
        print(header, flush=True)

    with conn.keepalive(on_event=on_event):
        start()
        if not done.wait(timeout):
            if pending:
                result.update(pending)
            else:
                result["state"] = "timeout"
                if verbose:
                    print(f"  TIMEOUT   after {timeout:.0f} s", flush=True)

    return result


def _pa_progress(frame):
    """Render one operation event as a short progress line, or ``None``.

    Shared by every blocking wrapper in this module (polar alignment,
    autofocus, goto).  Only the events that say something about progress
    are rendered; the firmware also interleaves ``PiStatus``, ``Exposure``
    and friends, which are noise here, and reports each finished operation
    twice (see :func:`_is_outer`) — the inner frame is dropped so a run
    doesn't print its result line twice.
    """
    ev = _event_name(frame)
    state = frame.get("state")

    if ev == "AutoFocus":
        if state == "start":
            return "  focus     sweeping focuser positions"
        if state == "working":
            pts = (frame.get("result") or {}).get("points") or []
            if pts:
                pos, fwhm = pts[-1]
                return f"  focus     pos={pos:<6} fwhm={fwhm:.3f}  ({len(pts)} pts)"
            return None
        if state == "complete":
            if not _is_outer(frame):
                return None
            return f"  FOCUSED   ({frame.get('lapse_ms', 0) / 1000:.1f} s)"
        if state in ("fail", "cancel"):
            if not _is_outer(frame):
                return None
            return (f"  {state.upper()}      {frame.get('error')} "
                    f"(code {frame.get('code')})")
        return None

    if ev == "FocuserMove" and state == "complete":
        return None                     # every focus step; too chatty

    if ev in ("AutoGoto", "AutoGotoStep"):
        if not _is_outer(frame):
            # Inner frames carry the useful per-attempt detail on failure.
            if state == "fail":
                return (f"  attempt   failed: {frame.get('error')} "
                        f"(code {frame.get('code')})")
            return None
        if state == "start":
            return "  goto      starting"
        if state == "working":
            return None
        if state == "complete":
            return (f"  ARRIVED   after {frame.get('count')} solve(s), "
                    f"{frame.get('lapse_ms', 0) / 1000:.1f} s")
        return (f"  {str(state).upper()}      {frame.get('error')} "
                f"(code {frame.get('code')})")

    if ev in ("ScopeHome", "ScopeMoveToHorizon"):
        if state == "working":
            return ("  parking   ..." if ev == "ScopeHome"
                    else "  opening   to the horizontal position")
        if state == "complete":
            extra = ""
            if ev == "ScopeHome":
                extra = f"  equ_mode={frame.get('equ_mode')}"
            return f"  DONE      ({frame.get('lapse_ms', 0) / 1000:.1f} s){extra}"
        return f"  {str(state).upper()}      {frame.get('error')}"

    if ev == "Alert":
        return f"  ALERT     {frame.get('error')} (code {frame.get('code')})"

    if ev == "ScopeTrack" and frame.get("error"):
        # 207 "fail to operate" is emitted routinely while parked/slewing.
        if frame.get("code") == 207:
            return None
        return (f"  tracking  {frame.get('error')} "
                f"(code {frame.get('code')})")

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
        if state in ("fail", "cancel"):
            return (f"  solve     {state}: {frame.get('error')} "
                    f"(code {frame.get('code')})")
        return f"  solving   {state}"

    if ev == "ScopeGoto":
        if state == "working":
            return "  slewing   ..."
        if state == "complete":
            line = f"  slewed    ({frame.get('lapse_ms', 0) / 1000:.1f} s)"
            ra_dec, dist = frame.get("cur_ra_dec"), frame.get("dist_deg")
            if ra_dec:
                line += f" ra={ra_dec[0]:.4f}h dec={ra_dec[1]:.4f}deg"
            if dist is not None:
                line += f" off by {dist * 60:.1f}'"
            return line
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
    what = (f"restart, dec_pos_index={dec_pos_index}" if restart
            else "re-measure at current position")
    return _await_operation(
        start=lambda: raw.start_polar_align(restart=restart,
                                            dec_pos_index=dec_pos_index),
        terminal="EqModePA",
        watch={"3PPA", "PlateSolve", "ScopeGoto", "MoveByAngle", "EqModePA"},
        extract=lambda f: {"total": f.get("total"), "x": f.get("x"),
                           "y": f.get("y"), "lapse_ms": f.get("lapse_ms")},
        verbose=verbose,
        timeout=timeout,
        header=f"Polar alignment on {conn.current_ip()} ({what})",
    )


@multiple_ips
def autofocus(verbose=True, timeout=180):
    """
    Run the auto-focus routine and block until it finishes.

    The firmware sweeps the focuser through a range of positions, measures
    star FWHM at each, fits the resulting V-curve and moves to its minimum.
    A typical sweep takes 25--45 s.

    A **view must already be running** — the routine focuses on whatever the
    camera is currently exposing, so with the camera idle it has no stars to
    measure and fails with ``'no star is detected'`` (code 279).  Call
    :func:`goto_target` (or :func:`~seestarpy.raw.iscope_start_view`) first.

    Like :func:`polar_align`, the firmware ties this operation to the TCP
    connection that started it, so the command is issued inside a
    :class:`~seestarpy.connection.keepalive` and this call blocks until the
    firmware reports a terminal state.

    Parameters
    ----------
    verbose : bool, optional
        Print a progress line per focus step, showing the focuser position
        and the measured FWHM. Default ``True``.
    timeout : float, optional
        Seconds to wait for the sweep to finish. Default ``180``.

    Returns
    -------
    dict
        ``{'state', 'position', 'lapse_ms', 'error', 'code'}``.  ``state`` is
        ``'complete'``, ``'fail'``, ``'cancel'`` or ``'timeout'``;
        ``position`` is the focuser position the routine settled on, read
        back after it finishes (``None`` if it could not be read).

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.

    Examples
    --------
    ::

        >>> import seestarpy as ssp
        >>> ssp.goto_target("NGC 3310")
        >>> res = ssp.autofocus()
        >>> res['position']
        1633

    """
    result = _await_operation(
        start=raw.start_auto_focuse,
        terminal="AutoFocus",
        watch={"AutoFocus", "FocuserMove"},
        extract=lambda f: {"lapse_ms": f.get("lapse_ms"),
                           "error": f.get("error"), "code": f.get("code")},
        verbose=verbose,
        timeout=timeout,
        header=f"Autofocus on {conn.current_ip()}",
    )

    # The AutoFocus event doesn't report where it settled, so read it back.
    try:
        pos = raw.get_focuser_position().get("result")
        if isinstance(pos, dict):
            pos = pos.get("step", pos.get("position"))
    except Exception:
        pos = None
    result["position"] = pos
    if verbose and pos is not None:
        print(f"  position  {pos}", flush=True)

    return result
