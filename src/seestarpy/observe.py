from src.seestarpy.connection import send_command


def set_eq_mode():
    params = {"method": "scope_park", "params": {"equ_mode": True}}
    return send_command(params)


def move_to_horizon():
    params = {'method': 'scope_move_to_horizon'}
    return send_command(params)


def park_scope():
    params = {'method': 'scope_park'}
    return send_command(params)


def goto(ra, dec):
    """
    ra : decimal hour angle [0, 24]
    dec : decimal declination [-90, 90]
    """
    params = {'method': 'scope_goto', 'params': [ra, dec]}
    return send_command(params)


def goto_target(target_name, ra, dec, use_lp_filter=False):
    """
    ra : decimal hour angle [0, 24]
    dec : decimal declination [-90, 90]
    """
    # params = {'method': 'scope_goto', 'params': [ra, dec]}
    params = {'method': 'iscope_start_view', 'params': {'mode': 'star',
                                                        'target_ra_dec': [ra, dec],
                                                        'target_name': target_name,
                                                        'lp_filter': use_lp_filter}}
    return send_command(params)


def set_track_state(flag):
    params = {'method': 'scope_set_track_state', "params": flag}
    return send_command(params)


def set_exposure(exptime, which="stack_l"):
    """which : [stack_l, continuous]"""
    params = {"method": "set_setting", "params": {"exp_ms": {which: exptime}}}
    return send_command(params)


def set_filter(pos):
    """
    0: Dark = Shutter closed
    1: Open = 400-700nm, with Bayer RGB matrix
    2: Narrow = 30 nm OIII (Blue) + 20 nm Hα (Red) (also LP: Light Pollution)
    """
    params = {"method": "set_wheel_position", "params": [pos]}
    return send_command(params)


def get_focuser_position():
    params = {"method": "get_focuser_position"}
    return send_command(params)


def set_focuser_position(pos):
    params = {"method": "move_focuser", "params": {"step": pos, "ret_step": True}}
    return send_command(params)


def stop_auto_focus():
    params = {"method": "stop_auto_focuse"}
    return send_command(params)


def create_dark():
    params = {"method": "start_create_dark"}
    return send_command(params)


def start_auto_focus():
    params = {"method": "start_auto_focuse"}
    return send_command(params)


def set_target_name(name):
    params = {"method": "set_sequence_setting", "params": [{"group_name": name}]}
    return send_command(params)
