from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import raw
from . import connection as conn
from .status import get_filter, is_eq_mode


def copy_doc(from_func):
    def decorator(to_func):
        to_func.__doc__ = from_func.__doc__
        return to_func
    return decorator


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
    """Opens the Seestar arm"""
    return raw.scope_move_to_horizon()


@multiple_ips
def close(eq_mode=None):
    """
    Closes the Seestar, and sets the mode to EQ or AzAlt

    Parameters
    ----------
    eq_mode : bool | None
        bool : explicitly set the EQ mode (True) or AzAlt (False)
        None : checks the current mode and uses that

    * Accepts the `ìps` keyword for sending the command to multiple Seestars simultaneously

    Examples
    --------
    ::
        >>> import seestarpy as ssp
        >>> ssp.close()             # Use the current value for EQ mode
        ...
        >>> ssp.close(False)        # Explicitly set the mount mode to AzAlt
        ...

    """
    eq_mode = is_eq_mode() if eq_mode is None else eq_mode
    return raw.scope_park(eq_mode)


@multiple_ips
@copy_doc(raw.scope_goto)
def goto(ra_dec=()):
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

    Parameters
    ----------
    flag : None | bool
        None : returns the tracking state
        bool : set the tracking state to on|off

    Returns
    -------
    dict : Return dictionary of relevant seestarpy.raw calls

    * Accepts the `ìps` keyword for sending the command to multiple Seestars simultaneously

    Examples
    --------
    ::
        >>> import seestarpy as ssp
        >>> ssp.tracking()
        False
        >>> ssp.tracking(False)     # Turn off tracking
        ...

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
    exptime : int | None
        None: returns the current exposure time
        int: sets the current exposure time. Accepted values in sec or milli-sec
    which : str, Optional
        Default: "stack_l". Set the long-exposure time. Options ["stack_l", "continuous"]

    * Accepts the `ìps` keyword for sending the command to multiple Seestars simultaneously


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
        ...

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
    Get/Set the filter wheel position

    Parameters
    ----------
    pos : int | str | None
        Returns the current filter wheel position with `None`
        Set the filter with any of: `[1, "open", "ircut", 2, "narrow", "lp"]`

    * Accepts the `ìps` keyword for sending the command to multiple Seestars simultaneously


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
    Get or set the focuser position

    Parameters
    ----------
    pos : None
        None : return the focuser position
        int : set the focuser position
        str : "auto" = start the auto-focus routine


    * Accepts the `ìps` keyword for sending the command to multiple Seestars simultaneously

    Examples
    --------
    >>> from seestarpy import filter_wheel
    >>> focuser()
    1580
    >>> focuser("auto")
    >>> focuser(pos=1605)
    ...

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
@copy_doc(raw.iscope_start_view)
def goto_target(target_name, ra, dec, lp_filter=False):
    return raw.iscope_start_view(ra, dec, target_name, lp_filter)


@multiple_ips
@copy_doc(raw.iscope_stop_view)
def stop_view():
    return raw.iscope_stop_view()


@multiple_ips
@copy_doc(raw.iscope_start_stack)
def start_stack(restart=True):
    return raw.iscope_start_stack(restart)


@multiple_ips
def set_eq_mode(equ_mode=True):
    return raw.scope_park(equ_mode)
