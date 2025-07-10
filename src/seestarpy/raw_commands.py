from datetime import datetime

from holoviews.examples.user_guide.Linked_Brushing import params

from src.seestarpy.connection import send_command

"""

iscope_start_stack
iscope_start_view
iscope_stop_view
move_focuser
pi_is_verified
pi_output_set2
pi_reboot
pi_shutdown
play_sound
scan_iscope
scope_goto
scope_park
scope_speed_move
scope_sync
set_control_value
set_sensor_calibration
set_sequence_setting
set_setting
set_stack_setting
start_auto_focuse
start_create_dark
start_polar_align
start_solve
stop_polar_align
"""

def get_albums():
    """
    Fetches a list of albums on the Seestar's internal disk

    Returns
    -------
    dict
        A dictionary containing the response data from the executed command.

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_albums()
        {'jsonrpc': '2.0',
         'Timestamp': '5076.313913578',
         'method': 'get_albums',
         'result': {'path': 'MyWorks',
                    'list': [ {'group_name': 'SolarSystem',
                               'files': [ {'name': 'Lunar',
                                           'thn': 'Lunar/2025-06-11-223602-Lunar_thn.jpg',
                                           'count': 2,
                                           'type': 0
                                           }
                                         ]
                                },
                               {'group_name': 'DeepSky',
                                'files': [ {'name': 'M 81',
                                            'thn': 'M 81/Stacked_37_M 81_10.0s_IRCUT_20250607-221810_thn.jpg',
                                            'count': 1,
                                            'type': 0
                                            },
                                           {'name': 'M 81_sub',
                                            'thn': 'M 81_sub/Light_M 81_10.0s_IRCUT_20250607-221746_thn.jpg',
                                            'count': 37,
                                            'type': 0
                                            },
                                         ]
                                 }
                             ]
                    },
         'code': 0,
         'id': 1}

    """
    params = {'method': 'get_albums'}
    return send_command(params)


def get_device_state(keys=None):
    """
    Returns a massive dictionary of device parameters

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_device_state(["location_lon_lat"])
        >>> raw.get_device_state()
        {'jsonrpc': '2.0',
         'Timestamp': '5286.347784540',
         'method': 'get_device_state',
         'result': {
             'device': {
                 'name': 'ASI AIR imager',
                 'svr_ver_string': '1.0',
                 'svr_ver_int': 29,
                 'firmware_ver_int': 2427,
                 'firmware_ver_string': '4.27',
                 'is_verified': True,
                 'sn': 'a3497936',
                 'cpuId': '5eb799bafdfee08c',
                 'product_model': 'Seestar S50',
                 'user_product_model': 'Seestar S50',
                 'focal_len': 250.0,
                 'fnumber': 5.0
                 },
             'setting': {
                'temp_unit': 'C',
                'beep_volume': 'close',
                'lang': 'en',
                'center_xy': [540, 960],
                'stack_lenhance': False,
                'heater_enable': False,
                'expt_heater_enable': False,
                'focal_pos': 1580,
                'factory_focal_pos': 1580,
                'exp_ms': {
                    'stack_l': 10000,
                    'continuous': 500
                    },
                'auto_power_off': True,
                'stack_dither': {
                    'pix': 50,
                    'interval': 5,
                    'enable': True
                    },
                'auto_3ppa_calib': True,
                'auto_af': False,
                'frame_calib': True,
                'calib_location': 2,
                'wide_cam': False,
                'stack_after_goto': True,
                'guest_mode': False,
                'user_stack_sim': False,
                'mosaic': {
                    'scale': 1.0,
                    'angle': 0.0,
                    'estimated_hours': 0.258333,
                    'star_map_angle': 361.0,
                    'star_map_ratio': 1.0
                    },
                'stack': {
                    'dbe': True,
                    'star_correction': True,
                    'cont_capt': False
                    },
                'ae_bri_percent': 50.0,
                'manual_exp': False,
                'isp_exp_ms': -999000.0,
                'isp_gain': -9990.0,
                'isp_range_gain': [0, 400],
                'isp_range_exp_us': [30, 1000000],
                'isp_range_exp_us_scenery': [30, 1000000]
                },
             'location_lon_lat': [14.7908, 47.9539],
             'camera': {
                 'chip_size': [1080, 1920],
                 'pixel_size_um': 2.9,
                 'debayer_pattern': 'GR',
                 'hpc_num': 2890
                 },
             'focuser': {
                 'state': 'idle',
                 'max_step': 2600, 'step': 1580},
             'ap': {
                 'ssid': 'S50_a3497936',
                 'passwd': '12345678',
                 'is_5g': False
                 },
             'station': {'server': True,
                 'freq': 2412,
                 'ip': '192.168.1.243',
                 'ssid': 'FTTH_CV2535',
                 'gateway': '192.168.1.1',
                 'netmask': '255.255.255.0',
                 'sig_lev': -88,
                 'key_mgmt': 'WPA2-PSK'
                 },
             'storage': {
                 'is_typec_connected': False,
                 'connected_storage': ['emmc'],
                 'storage_volume': [{
                     'name': 'emmc',
                     'state': 'mounted',
                     'total_mb': 51854,
                     'totalMB': 51854,
                     'free_mb': 36549,
                     'freeMB': 36549,
                     'disk_mb': 59699,
                     'diskSizeMB': 59699,
                     'used_percent': 38}],
                'cur_storage': 'emmc'},
             'balance_sensor': {
                'code': 0,
                'data': {
                    'x': 0.007797,
                    'y': -0.006858,
                    'z': 1.001298,
                    'angle': 0.594461
                    }
                },
             'compass_sensor': {
                'code': 0,
                'data': {
                    'x': 58.200001,
                    'y': 1.05,
                    'z': -18.150002,
                    'direction': 91.43029,
                    'cali': 0
                    }
                },
             'mount': {
                'move_type': 'none',
                'close': True,
                'tracking': False,
                'equ_mode': False
                },
             'pi_status': {
                'is_overtemp': False,
                'temp': 49.599998,
                'charger_status': 'Discharging',
                'battery_capacity': 48,
                'charge_online': False,
                'is_typec_connected': False,
                'battery_overtemp': False,
                'battery_temp': 23,
                'battery_temp_type': 'normal'
                }
             },
         'code': 0,
         'id': 1}

    """
    if keys is None:
        keys = []
    params = {"method": "get_device_state",
              "params": {"keys": keys}}
    return send_command(params)


def get_camera_state():
    params = {"method": "get_camera_state"}
    return send_command(params)


def get_event_state():
    params = {"method": "get_event_state"}
    return send_command(params)


def get_view_state():
    params = {"method": "get_view_state"}
    return send_command(params)


def get_focuser_position():
    """
    Returns the position of the focuser in the range (1200, 2600)

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_focuser_position()

    """
    params = {"method": "get_focuser_position"}
    return send_command(params)


def get_user_location():
    params = {'method': 'get_user_location'}
    return send_command(params)


def get_solve_result():
    params = {"method": "get_solve_result"}
    return send_command(params)


def get_sensor_calibration():
    """
    Get compass sensor calibration data

    Returns
    -------

    """
    params = {"method": "get_sensor_calibration"}
    return send_command(params)


def get_setting(which=None):
    """
    Gets the settings dict

    Parameters
    ----------
    which : list or None

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_setting()

    """
    if which is None:
        which = []
    params = {"method": "get_setting", "params": {"keys": which}}
    return send_command(params)


def iscope_get_app_state():
    params = {"method": "iscope_get_app_state"}
    return send_command(params)


def iscope_start_view(in_ra, in_dec, target_name="Unknown", lp_filter=False, mode="star"):
    """
    Start viewing a target, but not stacking the incoming frames.

    This involves doing a goto to the target and selecting the LP filter

    Parameters
    ----------
    in_ra, in_dec: float
        Decimal hour angle, Decimal degrees
    target_name : str
        Default: "Unknown", Name of the target, which also defines the directory
        name on the emmc drive
    lp_filter : boool
        Default: False, use the light pollution filter
    mode : str
        Default "star"

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_setting()

    """
    params = {"method": "iscope_start_view",
              "params": {"mode": mode,
                         "target_ra_dec": [in_ra, in_dec],
                         "target_name": target_name,
                         "lp_filter": lp_filter
                         }
              }
    return send_command(params)


def iscope_stop_view(stage="AutoGoto"):
    """TODO: What does stage do?

    Parameters
    ----------
    stage : str
        ["AutoGoto", "Stack", ]

    """

    params = {"method": "iscope_stop_view",
              "params": {"stage": stage}}
    return send_command(params)


def iscope_start_stack(restart=True):
    """

    Parameters
    ----------
    restart: bool

    Returns
    -------

    """
    params = {"method": "iscope_start_stack",
              "params": {"restart": restart}
              }
    return send_command(params)


def move_focuser(pos, retry=True):
    """
    Move the focuser to the given position in the range (1200, 2600)

    Parameters
    ----------
    pos : int
        Factory default is 1580
    retry : bool
        Retry finding position

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.move_focuser(1605)

    """
    params = {"method": "move_focuser",
              "params": {"step": pos,
                         "ret_step": retry}
              }
    return send_command(params)


def pi_get_time():
    params = {'method': 'pi_get_time'}
    return send_command(params)


def pi_set_time():
    now = datetime.now()
    print(now)
    date_json = {"year": now.year,
                 "mon": now.month,
                 "day": now.day,
                 "hour": now.hour,
                 "min": now.minute,
                 "sec": now.second,
                 "time_zone": "Australia/Melbourne"}
    params = {'method': 'pi_set_time', 'params': [date_json]}
    return send_command(params)


def pi_reboot():
    params = {'method': 'pi_reboot'}
    return send_command(params)


def pi_shutdown(force=False):
    params = {'method': 'pi_shutdown'}
    return send_command(params) if force else "Are you sure you want to shutdown? Then use force=True"


def pi_is_verified():
    params = {'method': 'pi_is_verified'}
    return send_command(params)


def pi_output_set2(is_dew_on=False, dew_heater_power=0):
    """
    Turn on dew heater

    Parameters
    ----------
    is_dew_on: bool
        Default: False
    dew_heater_power: int
        Default: 0, TODO: Is this percent?

    Returns
    -------
    dict

    """
    params = {'method': 'pi_output_set2',
              "params": {"heater": {"state": is_dew_on,
                                    "value": dew_heater_power}
                         }
              }
    return send_command(params)


def play_sound(sound_id):
    """
    Plays a sound from the internal soundboard.

    Parameters
    ----------
    sound_id: int
        [13, 80, 82, 83]

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.play_sound(80)

    """
    params = {'method': 'play_sound', 'params': {"num": sound_id}}
    return send_command(params)


def set_setting(**kwargs):
    """
    Sets values in the seestar settings dictionary

    (Theoretically) should accept any of the key arguments that are returned
    with 'get_setting'

    Parameters
    ----------
    temp_unit: string
        ['C' 'F']
    beep_volume: string or int
        'close'
    lang: string
        ['en', ?]
    center_xy: list of ints
        Default: [540, 960] Defined by the chip size. Not settable.
    stack_lenhance: bool
        Default: True. Enables dark subtraction. NOTE - Needs own call as it moves the filter.
    heater_enable: bool
        Default: False. Turn on dew heater
    expt_heater_enable: bool
        Default: False              # TODO: No idea what this means
    focal_pos: int
        Current focuser position. Acceptable range [1200 to 2600]
    factory_focal_pos: int
        Factory default is 1580.
    exp_ms': dict
        {'stack_l': 10000,      # [ms] For stacking
         'continuous': 500      # [ms] For "live view"
         }
    auto_power_off: bool
        Default True. Turns off the Seestar if no open connection and not exposing for 15 mins (?)
    stack_dither:
        {"pix": 50,             # Number of pixels in dither pattern throw
         "interval": 0,         # TODO: Uncertain if this is millisec or sec
         "enable": False        # Use dithering function
         }
    auto_3ppa_calib: bool
        Defualt: True. Turn on automatic 3-point polar-alignment calibration
    auto_af: bool
        Defualt: False. auto_af was introduced in recent firmware that seems to perform autofocus after a goto.
    frame_calib: bool
        Default: True.              # TODO: no idea what this means
    calib_location: int
        Default: 2.                 # TODO: no idea what this means
    wide_cam: bool
        Default: False              # TODO: no idea what this means
    stack_after_goto: bool
        Default: True. stack_after_goto is in 2.1+ firmware. Note: Disable if possible
    guest_mode: bool
        Default: False              # TODO: No idea what this means
    user_stack_sim: bool
        Default: False              # TODO: No idea what this means
    mosaic: dict
        {'scale': 1.0,                  # TODO: No idea what this means
         'angle': 0.0,                  # TODO: No idea what this means
         'estimated_hours': 0.258333,   # TODO: No idea what this means
         'star_map_angle': 361.0,       # TODO: No idea what this means
         'star_map_ratio': 1.0          # TODO: No idea what this means
         },
    stack: dict
        {'dbe': True,               # TODO: No idea what this means
         'star_correction': True,   # TODO: No idea what this means
         'cont_capt': False         # TODO: No idea what this means
         }
    ae_bri_percent: float
        Default: 50.0.              # TODO: No idea what this means
    manual_exp: bool
        Default: False              # TODO: No idea what this means
    isp_exp_ms': float
        Default: -999000.0,         # TODO: No idea what this means
    isp_gain: float
        Default: -9990.0,           # TODO: No idea what this means
    isp_range_gain: list
        Default: [0, 400],          # TODO: No idea what this means
    isp_range_exp_us: list
        Default: [30, 1000000],     # TODO: No idea what this means
    isp_range_exp_us_scenery: list
        Default: [30, 1000000],     # TODO: No idea what this means

    Returns
    -------
    dict

    Examples
    --------


    """
    params_dict = {
        "temp_unit": "C",               # Default to Celsius
        "beep_volume": "close",
        "lang": "en",
        "center_xy": [540, 960],        # Not settable, defined by chip size
        "stack_lenhance": True,         # Enables dark subtraction
        "heater_enable": False,         # Turn on dew heater
        "expt_heater_enable": False,
        "focal_pos": 1580,              # Using factory default as initial value
        "factory_focal_pos": 1580,
        "exp_ms": {
            "stack_l": 10000,           # [ms] For stacking
            "continuous": 500           # [ms] For "live view"
        },
        "auto_power_off": True,         # Turns off after 15 mins of inactivity
        "stack_dither": {
            "pix": 50,                  # Number of pixels in dither pattern throw
            "interval": 0,              # Uncertain if millisec or sec
            "enable": False             # Use dithering function
        },
        "auto_3ppa_calib": True,        # Automatic 3-point polar-alignment calibration
        "auto_af": False,  # Autofocus after goto
        "frame_calib": True,
        "calib_location": 2,
        "wide_cam": False,
        "stack_after_goto": True,  # In 2.1+ firmware
        "guest_mode": False,
        "user_stack_sim": False,
        "mosaic": {
            "scale": 1.0,
            "angle": 0.0,
            "estimated_hours": 0.258333,
            "star_map_angle": 361.0,
            "star_map_ratio": 1.0
        },
        "stack": {
            "dbe": True,
            "star_correction": True,
            "cont_capt": False
        },
        "ae_bri_percent": 50.0,
        "manual_exp": False,
        "isp_exp_ms": -999000.0,
        "isp_gain": -9990.0,
        "isp_range_gain": [0, 400],
        "isp_range_exp_us": [30, 1000000],
        "isp_range_exp_us_scenery": [30, 1000000],
        "master_cli": True  # Keeping this from original as it seems important
    }
    params_dict.update(kwargs)
    params = {"method": "set_setting", "params": params_dict}
    return send_command(params)


def set_stack_setting(save_ok_frames=True, save_rejected_frames=False):
    """
    Save individual frames to emmc.

    Parameters
    ----------
    save_ok_frames : bool
        Default: True. Save accepted individual frames to emmc.
    save_rejected_frames : bool
        Default: False. Save rejected individual frames to emmc.

    Returns
    -------

    """
    params = {"method": "set_stack_setting",
              "params": {"save_discrete_ok_frame": True,
                         "save_discrete_frame": False
                         }
              }
    return send_command(params)


def set_user_location(lat, lon):
    """
    Set the location on earth of the user

    Parameters
    ----------
    lat, lon: float
        Decimal degrees, positive for North and East.

    Returns
    -------
    dict

    """
    params = {'method': 'set_user_location',
              'params': {'lat': lat,
                         'lon': lon,
                         'force': True}}
    return send_command(params)


def set_wheel_position(pos):
    """
    Set the filter-wheel position.

    Parameters
    ----------
    pos: int
        0: Dark = Shutter closed
        1: Open = 400-700nm, with Bayer RGB matrix
        2: Narrow = 30 nm OIII (Blue) + 20 nm Hα (Red) (also LP: Light Pollution)
    """
    params = {"method": "set_wheel_position", "params": [pos]}
    return send_command(params)


def set_sequence_setting(name):
    params = {"method": "set_sequence_setting",
              "params": [{"group_name": name}]}
    return send_command(params)


def set_control_value(gain=80):
    """
    Used for setting gain parameter at the moment

    Parameters
    ----------
    gain: int
        Default: 80

    Returns
    -------
    dict

    """
    params = {"method": "set_control_value", "params": ["gain", gain]}
    return send_command(params)


def set_sensor_calibration(x, y, z, x11, x12, y11, y12):
    """
    Override device's compass bearing to account for the magnetic declination 
    at device's position.
    
    Parameters
    ----------
    x, y, z : float

    x11, x12, y11, y12 : float
        Rotation matrix coefficients.

    Returns
    -------

    """
    params = {"method": "set_sensor_calibration",
              "params": {"compassSensor": {"x": x,
                                           "y": y,
                                           "z": z,
                                           "x11": x11,
                                           "x12": x12,
                                           "y11": y11,
                                           "y12": y12,}
                         }
              }
    return send_command(params)


def scope_move_to_horizon():
    """
    Moves the scope arm to the horizontal position.

    This is necessary to turn the Seestar on. You cannot move to an object
    directly from the park position

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.scope_move_to_horizon()

    """
    params = {'method': 'scope_move_to_horizon'}
    return send_command(params)


def scope_park(set_eq_mode=False):
    """
    Moves the scope arm to the park position.

    This essentially turns the Seestar off.
    To put the Seestar into EQ mode, you first need to move_to_horizon and then
    scope_park(True).

    Parameters
    ----------
    set_eq_mode: bool
        Default: False. Set the equatorial mode.

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.scope_park()
        >>> raw.scope_park(set_eq_mode=True)

    """
    params = {'method': 'scope_park',
              "params": {"equ_mode": set_eq_mode}}
    return send_command(params)


def scope_goto(ra, dec):
    """
    Move the scope arm to the given ra, dec coordinates.

    Parameters
    ----------
    ra, dec : float
        Decimal hour angle [0, 24] and declination [-90, 90]

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.scope_goto(13.4, 54.8)          # Mizar
        >>> raw.scope_goto(18.082, -24.3)       # M8 Lagoon Nebula
        >>> raw.scope_goto(5.63, -69.4)         # 30 Dor in LMC (Tarantula Nebula)
        >>> raw.scope_goto(0.398, -72.2)        # 47 Tuc globular cluster (SMC)

    """
    params = {'method': 'scope_goto', 'params': [ra, dec]}
    return send_command(params)


def scope_set_track_state(flag):
    """
    Turns the Seestar tracking state on/off.

    Parameters
    ----------
    flag : bool

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.scope_set_track_state(True)

    """
    params = {'method': 'scope_set_track_state', "params": flag}
    return send_command(params)


def scope_get_track_state():
    params = {'method': 'scope_get_track_state'}
    return send_command(params)


def scope_get_equ_coord():
    params = {'method': 'scope_get_equ_coord'}
    return send_command(params)


def scope_get_horiz_coord():
    params = {'method': 'scope_get_horiz_coord'}
    return send_command(params)


def scope_sync(in_ra, in_dec):
    """

    Parameters
    ----------
    in_ra, in_dec: float
        Decimal hour angle, Decimal degrees

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.scope_sync(13.4, 54.8)          # Mizar

    """
    params = {'method': 'scope_sync', "params": [in_ra, in_dec]}
    return send_command(params)


def scope_speed_move(speed=4000, angle=270, dur_sec=10):
    """
    Moving the scope arm with a given speed and angle for a given duration.
    TODO: What do the values actually mean? Is this just the Dec-arm?

    Parameters
    ----------
    speed: int
        TODO: Is this in arcsec/sec?
    angle: int
        TODO: How does this relate to the Dec-arm?
    dur_sec: int
        TODO: Does this mean the time to complete the move?

    Returns
    -------
    dict

    Examples
    --------
    ::
    from seestarpy import raw
    raw.scope_speed_move(speed=5000, angle=270, dur_sec=2)

    """
    params = {"method": "scope_speed_move",
              "params": {"speed": speed, "angle": angle, "dur_sec": dur_sec}}
    return send_command(params)


def start_create_dark():
    params = {"method": "start_create_dark"}
    return send_command(params)


def start_auto_focuse():
    params = {"method": "start_auto_focuse"}
    return send_command(params)


def start_solve():
    params = {"method": "start_solve"}
    return send_command(params)


def start_polar_align(restart=True, dec_pos_index=3):
    """
    Run the polar alignment sequence

    Parameters
    ----------
    restart : bool
        Default: True.
    dec_pos_index: int
        TODO: Find out what this means

    Returns
    -------
    dict

    """
    params = {"method": "start_polar_align",
              "params": {"restart": restart,
                         "dec_pos_index": dec_pos_index}
              }
    return send_command(params)


def stop_auto_focuse():
    params = {"method": "stop_auto_focuse"}
    return send_command(params)


def stop_polar_align():
    params = {"method": "stop_polar_align"}
    return send_command(params)


def stop_scheduler():
    params = {"method": "stop_scheduler"}
    return send_command(params)


def stop_goto_target():
    params = {"method": "stop_goto_target"}
    return send_command(params)


def stop_plate_solve_loop():
    params = {"method": "stop_plate_solve_loop"}
    return send_command(params)


def test_connection():
    params = {'method': 'test_connection'}
    return send_command(params)
