from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import raw
from . import connection as conn
from .status import get_filter, is_eq_mode



def multiple_ips(func):
    """
    Decorator that allows a function to run against multiple IP addresses.
    Pass `ips` at call time to override DEFAULT_IP.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract the ips list from call arguments
        call_time_ips = kwargs.pop('ips', None)

        def resolve_ip(ip):
            print(ip)
            # Use provided IPs or default to current DEFAULT_IP
            if isinstance(ip, list):
                return [resolve_ip(ip) for ip in ip]
            elif isinstance(ip, str):
                if ip in conn.AVAILABLE_IPS:
                    return conn.AVAILABLE_IPS[ip]
                elif ip in conn.AVAILABLE_IPS.values():
                    return ip
                else:
                    print(f"{ip} is not a valid IP address")
                    return None
            elif isinstance(ip, int):
                name = f"seestar-{ip}.local" if ip > 1 else "seestar.local"
                return resolve_ip(name)
            elif ip is None:
                return conn.DEFAULT_IP

        if isinstance(call_time_ips, str) and call_time_ips.lower() == "all":
            call_time_ips = list(conn.AVAILABLE_IPS.values())
        if not isinstance(call_time_ips, list):
            call_time_ips = [call_time_ips]
        ips = resolve_ip(call_time_ips)

        def call_with_ip(ip):
            """Helper function to call the original function with a specific IP"""
            conn.DEFAULT_IP = ip
            print(f"{func.__name__}: call to {ip}")
            return func(*args, **kwargs)

        results = {}
        original_ip = conn.DEFAULT_IP  # Save the original IP

        try:
            with ThreadPoolExecutor(max_workers=len(ips)) as executor:
                # Submit all tasks
                future_to_ip = {executor.submit(call_with_ip, ip): ip for ip in
                                ips}

                # Collect results as they complete
                for future in future_to_ip:
                    ip = future_to_ip[future]
                    results[ip] = future.result()

        finally:
            conn.DEFAULT_IP = original_ip  # Always restore the original IP

        # Return single result if only one IP, otherwise return list
        return list(results.values())[0] if len(results) == 1 else results

    return wrapper


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
def goto_target(target_name, ra, dec, lp_filter=False):
    """
    Slew to a target by name and coordinates, then start viewing.

    This triggers an ``AutoGoto`` sequence: the telescope slews to the
    given coordinates, runs a plate-solve loop, and then enters
    ``ContinuousExposure`` mode.

    Parameters
    ----------
    target_name : str
        Name of the target. Also used as the directory name on the
        Seestar's internal storage.
    ra : float
        Right Ascension in decimal hours.
    dec : float
        Declination in decimal degrees.
    lp_filter : bool, optional
        Use the light-pollution filter. Default is ``False``.

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
        >>> ssp.goto_target("Mizar", ra=13.4, dec=54.9)
        >>> ssp.goto_target("M8", ra=18.06, dec=-24.38, lp_filter=True)

    """
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
        >>> ssp.goto_target("M31", ra=0.712, dec=41.27)
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
