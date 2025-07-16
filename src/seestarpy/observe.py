from .connection import send_command


def set_eq_mode(equ_mode=True):
    params = {"method": "scope_park", "params": {"equ_mode": equ_mode}}
    return send_command(params)


def goto_target(target_name, ra, dec, use_lp_filter=False):
    """
    ra, dec : float
        decimal hour angle [0, 24], decimal declination [-90, 90]
    """
    # params = {'method': 'scope_goto', 'params': [ra, dec]}
    params = {'method': 'iscope_start_view', 'params': {'mode': 'star',
                                                        'target_ra_dec': [ra, dec],
                                                        'target_name': target_name,
                                                        'lp_filter': use_lp_filter}}
    return send_command(params)


def set_exposure(exptime, which="stack_l"):
    """which : [stack_l, continuous]"""
    params = {"method": "set_setting", "params": {"exp_ms": {which: exptime}}}
    return send_command(params)


