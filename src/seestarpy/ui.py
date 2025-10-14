from .connection import send_command
from .observe import set_exposure
from .raw import scope_move_to_horizon, scope_park, \
    scope_set_track_state, get_focuser_position, move_focuser, \
    start_auto_focuse, scope_get_track_state, set_wheel_position, scope_goto
from .status import get_exposure, get_filter


def move(ra_dec=()):
    if isinstance(ra_dec, (tuple, list)) and len(ra_dec) == 2:
        return scope_goto(*ra_dec)
    elif isinstance(ra_dec, str):
        if ra_dec.lower() == "park":
            return scope_park()
        elif ra_dec.lower() == "horizon":
            return scope_move_to_horizon()
    else:
        raise ValueError(
            f"ra_dec must be one of: [(ra, dec), 'park', 'horizon']: {ra_dec}")


def tracking(flag=None):
    if flag is None:
        return scope_get_track_state()
    elif isinstance(flag, bool):
        return scope_set_track_state(flag)
    else:
        raise ValueError(f"flag must be one of: [None, True, False]: {flag}")


def exposure(exptime=None, stack_l=True):
    if exptime is None:
        return get_exposure()
    elif isinstance(exptime, int) and isinstance(stack_l, bool):
        return set_exposure(exptime, stack_l)
    else:
        raise ValueError(f"exptime must be one of [None, int]: {exptime}, and stack_l must be boolean: {stack_l}")


def filter_wheel(pos=None):
    if pos is None:
        return get_filter()
    elif isinstance(pos, int):
        return set_wheel_position(pos)
    elif isinstance(pos, str) and pos.lower() in ["open", "narrow"]:
        pos_i = {"open": 1, "narrow": 2, "lp": 2}[pos]
        return set_wheel_position(pos)


def focuser(pos: int | None = None):
    """

    Parameters
    ----------
    pos : None

    Returns
    -------

    """
    if pos is None:
        return get_focuser_position()
    elif isinstance(pos, int):
        return move_focuser(pos)
    elif isinstance(pos, str) and pos.lower() =="auto":
        return start_auto_focuse()
    else:
        raise ValueError(f"pos must be one of [None, int, 'auto']: {pos}")


def start_view():
    params = {"method": "iscope_start_view"}
    return send_command(params)


def stop_view():
    params = {"method": "iscope_stop_view"}
    return send_command(params)


def start_stack():
    params = {"method": "iscope_start_stack"}
    return send_command(params)


def random_command(cmd, params=None, force=False):
    params = {"method": cmd, "params": params}
    if "shutdown" in cmd and not force:
        raise ValueError(f"Not executing shutdown command, unless you specify `force=True`: {cmd=}, {force=}")
    return send_command(params)