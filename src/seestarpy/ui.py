from . import connection as conn
from . import raw
from .status import get_exposure, get_filter


def copy_doc(from_func):
    def decorator(to_func):
        to_func.__doc__ = from_func.__doc__
        return to_func
    return decorator


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


def tracking(flag=None):
    if flag is None:
        return raw.scope_get_track_state()
    elif isinstance(flag, bool):
        return raw.scope_set_track_state(flag)
    else:
        raise ValueError(f"flag must be one of: [None, True, False]: {flag}")


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


@copy_doc(raw.iscope_start_view)
def start_view(**kwargs):
    return raw.iscope_start_view(**kwargs)


@copy_doc(raw.iscope_stop_view)
def stop_view():
    return raw.iscope_stop_view()


@copy_doc(raw.iscope_start_stack)
def start_stack(restart=True):
    return raw.iscope_start_stack(restart)


def set_exposure(exptime, which="stack_l"):
    """which : [stack_l, continuous]"""
    raw.set_setting({"exp_ms": {which: exptime}})
    params = {"method": "set_setting", "params": {}}
    return send_command(params)
