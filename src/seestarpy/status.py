from src.seestarpy.connection import send_command


def get_device_state():
    params = {"method": "get_device_state"}
    return send_command(params)


def get_mount_state():
    params = {"method": "get_device_state", "params": {"keys":["mount"]}}
    payload = send_command(params)
    return payload["result"]["mount"]


def is_eq_mode():
    return get_mount_state()["equ_mode"]


def is_tracking():
    return get_mount_state()["tracking"]


def is_parked():
    return get_mount_state()["close"]


def get_app_state():
    params = {"method": "iscope_get_app_state"}
    return send_command(params)


def get_camera_state():
    params = {"method": "get_camera_state"}
    return send_command(params)


def get_view_state():
    params = {"method": "get_view_state"}
    return send_command(params)


def get_coords():
    # params = {'method': 'scope_get_equ_coord'}
    params = {'method': 'scope_get_ra_dec'}
    eq_dict = send_command(params)
    params = {'method': 'scope_get_horiz_coord'}
    altaz_dict = send_command(params)

    if (isinstance(eq_dict.get("result"), list) and
            isinstance(altaz_dict.get("result"), list)):
        return {"ra": eq_dict["result"][0],
                "dec": eq_dict["result"][1],
                "alt": altaz_dict["result"][0],
                "az": altaz_dict["result"][1]}
    else:
        raise ValueError(f"Could not get coordinates: {eq_dict}, {altaz_dict}")


def get_track_state():
    params = {'method': 'scope_get_track_state'}
    return send_command(params)


def get_exposure(which="stack_l"):
    """which : [stack_l, continuous]"""
    params = {"method": "get_setting", "params": {"keys": ["exp_ms"]}}
    payload = send_command(params)
    return payload["result"]["exp_ms"][which]


def get_filter():
    params = {"method": "get_wheel_position"}
    return send_command(params)


def get_target_name():
    params = {"method": "get_sequence_setting"}
    return send_command(params).get("group_name")


def get_target_name2():
    params = {"method": "get_img_name_field"}
    return send_command(params)
