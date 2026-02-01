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
    Pass ip_list at call time to override DEFAULT_IP.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Extract ip_list from call arguments
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
    return raw.scope_move_to_horizon()


@multiple_ips
def close(eq_mode=None):
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
    if flag is None:
        return raw.scope_get_track_state()
    elif isinstance(flag, bool):
        return raw.scope_set_track_state(flag)
    else:
        raise ValueError(f"flag must be one of: [None, True, False]: {flag}")


@multiple_ips
def exposure(exptime: int | None = None, which="stack_l"):
    """

    Parameters
    ----------
    exptime

    Returns
    -------

    """
    if exptime is None:
        return raw.get_setting().get("result", {}).get("exp_ms")
    elif isinstance(exptime, int):
        return raw.set_setting(exp_ms={which: exptime})
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
def focuser(pos: int | None = None):
    """

    Parameters
    ----------
    pos : None

    Returns
    -------

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
