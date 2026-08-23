import functools
import warnings
from datetime import datetime

from tzlocal import get_localzone_name  # pip install tzlocal


def _deprecated(since, message=""):
    """Mark a function as deprecated, emitting a warning when called."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func.__name__} is deprecated since {since}. {message}",
                DeprecationWarning,
                stacklevel=2,
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator

from .connection import send_command, multiple_ips, current_ip


@multiple_ips
def get_albums():
    """
    Fetches a list of albums on the Seestar's internal disk

    Returns
    -------
    dict
        A dictionary containing the response data from the executed command.

    Examples
    --------

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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'get_albums'}
    return send_command(params)


@multiple_ips
def get_img_file_page_number(directory, skip_avi=False):
    """
    Get the total number of pages for files in a directory on the Seestar.

    This sets the directory context on the firmware. Subsequent calls to
    :func:`get_img_file_page_name` page through that context. Each page
    contains up to 20 items.

    Parameters
    ----------
    directory : str
        Path relative to the eMMC root (e.g. ``"MyWorks/M 81_sub"``).
    skip_avi : bool, optional
        If ``True``, exclude AVI video files from the listing.
        Default is ``False``.

    Returns
    -------
    dict
        Response with ``result`` as an integer page count.

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_img_file_page_number("MyWorks/M 81_sub")
        {'result': 3, 'code': 0, ...}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_img_file_page_number",
              "params": {"dir": directory, "skip_avi": skip_avi}}
    return send_command(params)


@multiple_ips
def get_img_file_page_name(page=0):
    """
    Get the file listing for a specific page (up to 20 items per page).

    Must be called after :func:`get_img_file_page_number`, which sets the
    directory context on the firmware.

    Parameters
    ----------
    page : int, optional
        Zero-indexed page number. Default is ``0``.

    Returns
    -------
    dict
        Response with ``result`` as a list of file entries, each containing:

        - ``name`` (str) — filename
        - ``date`` (str) — modification date
        - ``size_k`` (int) — size in KB
        - ``is_dir`` (bool) — directory flag
        - ``file_cnt`` (int) — child count (for directories)
        - ``avi_duration_sec`` (Number or null) — video duration

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_img_file_page_number("MyWorks/M 81_sub")
        >>> raw.get_img_file_page_name(0)
        {'result': [{'name': 'Light_M 81_10.0s_...fit', 'size_k': 4050, ...}, ...]}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_img_file_page_name",
              "params": {"page": page}}
    return send_command(params)



@multiple_ips
def get_camera_info():
    """
    Returns info on the cameras

    Returns
    -------
    dict

    Examples
    --------

    >>> from seestarpy import raw
    >>> raw.get_camera_info()
    {'jsonrpc': '2.0',
     'Timestamp': '3210.498389760',
     'method': 'get_camera_info',
     'result': {'chip_size': [1080, 1920],
      'bins': [1, 2],
      'pixel_size_um': 2.9,
      'unity_gain': 0,
      'has_cooler': False,
      'is_color': True,
      'is_usb3_host': False,
      'has_hpc': False,
      'debayer_pattern': 'GR'},
     'code': 0,
     'id': 1}


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_camera_info"}
    return send_command(params)


@multiple_ips
def get_camera_state():
    """
    Return the name and state of the camera.

    Returns
    -------
    dict

    Examples
    --------

    >>> from seestarpy import raw
    >>> raw.get_camera_state()
    {'jsonrpc': '2.0',
     'Timestamp': '3340.447572824',
     'method': 'get_camera_state',
     'result': {'state': 'idle',
      'name': 'Seestar S50',
      'path': 'on-board-Seestar S50'},
     'code': 0,
     'id': 1}


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_camera_state"}
    return send_command(params)


@multiple_ips
def get_device_state(keys=None):
    """
    Returns a massive dictionary of device parameters

    Parameters
    ----------
    keys: list of str | None
        If not None, then only top-level keys can be specificed. See examples.

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_device_state(["location_lon_lat", "mount"])
        {'jsonrpc': '2.0',
         'Timestamp': '3523.643992366',
         'method': 'get_device_state',
         'result': {
             'location_lon_lat': [14.7908, 47.9539],
             'mount': {
                 'move_type': 'none',
                 'close': False,
                 'tracking': False,
                 'equ_mode': False
             }
         },
         'code': 0,
         'id': 1}

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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    if keys is None:
        keys = []
    params = {"method": "get_device_state",
              "params": {"keys": keys}}
    return send_command(params)


@multiple_ips
def get_disk_volume():
    """
    Returns the information on the internal emmc drive: totalMB and freeMB

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.get_disk_volume()
        {'jsonrpc': '2.0',
         'Timestamp': '3792.755156509',
         'method': 'get_disk_volume',
         'result': {'totalMB': 51854, 'freeMB': 36549},
         'code': 0,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_disk_volume"}
    return send_command(params)



@multiple_ips
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
        {'jsonrpc': '2.0',
         'Timestamp': '3929.576517861',
         'method': 'get_focuser_position',
         'result': 1605,
         'code': 0,
         'id': 1}


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_focuser_position"}
    return send_command(params)


@multiple_ips
def get_last_solve_result():
    """
    Get the result of the last plate-solve attempt.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import raw
        >>> raw.get_last_solve_result()
        {'jsonrpc': '2.0',
         'Timestamp': '3957.619006162',
         'method': 'get_last_solve_result',
         'error': 'no solve data',
         'code': 215,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_last_solve_result"}
    return send_command(params)


@multiple_ips
def get_solve_result():
    """
    Get the current plate-solve result.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import raw
        >>> raw.get_solve_result()
        {'jsonrpc': '2.0',
         'Timestamp': '3957.619006162',
         'method': 'get_solve_result',
         'error': 'no solve data',
         'code': 215,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_solve_result"}
    return send_command(params)


@multiple_ips
@_deprecated("v0.1.2", message="Seestar Firmware v6.7 uses 'get_setting'")
def get_stack_setting():
    """
    Find out whether the Seestar is saving all sub-frames, good and bad.

    .. deprecated::
        The ``get_stack_setting`` RPC method was removed from the firmware
        at v6.7; on newer firmware (e.g. v7.x / v8.x) it returns
        ``code 103`` (``"method not found"``).  This wrapper is now
        **firmware-tolerant**: it tries ``get_stack_setting`` first (so old
        scopes keep their native response) and, if the firmware rejects it
        with ``code 103``, transparently falls back to
        :func:`get_setting`.  Prefer :func:`get_setting` directly on modern
        firmware.

    Returns
    -------
    dict
        On old firmware, the native ``get_stack_setting`` response (see the
        example below).  On firmware that removed the method, the
        :func:`get_setting` response, whose ``result`` carries the stacking
        settings among the full settings dict.

    Examples
    --------
    ::

        >>> from seestarpy import raw
        >>> raw.get_stack_setting()
        {'jsonrpc': '2.0',
         'Timestamp': '4074.257331529',
         'method': 'get_stack_setting',
         'result': {
            'save_discrete_frame': False,
            'save_discrete_ok_frame': True,
            'light_duration_min': -1
            },
         'code': 0,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    resp = send_command({"method": "get_stack_setting"})
    # Firmware >= v6.7 removed this method and answers "method not found"
    # (code 103).  Fall back to get_setting, which carries these settings.
    if isinstance(resp, dict) and resp.get("code") == 103:
        return send_command({"method": "get_setting"})
    return resp


@multiple_ips
def get_stack_info():
    """
    Get the dimensions of the current stacked image.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import raw
        >>> raw.get_stack_info()
        {'jsonrpc': '2.0',
         'Timestamp': '4034.734550212',
         'method': 'get_stack_info',
         'result': {'width': 0, 'height': 0},
         'code': 0,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_stack_info"}
    return send_command(params)


@multiple_ips
def get_sensor_calibration():
    """
    Get compass sensor calibration data.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import raw
        >>> raw.get_sensor_calibration()
        {'jsonrpc': '2.0',
         'Timestamp': '4183.724277609',
         'method': 'get_sensor_calibration',
         'result': {'balanceSensor': {'x': -0.016068,
           'y': 0.024697,
           'z': 0.007157,
           'exist': True},
          'compassSensor': {'x': 75.3092,
           'y': 1.72128,
           'z': 0.0,
           'x11': 1.44953,
           'x12': -0.068635,
           'y11': -0.068635,
           'y12': 1.48135,
           'exist': True}},
         'code': 0,
         'id': 1}


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_sensor_calibration"}
    return send_command(params)


@multiple_ips
def get_setting():
    """
    Gets the settings dict. No option to select individual keys.

    This is basically the equivalent to `get_device_state(["setting"])`

    Returns
    -------
    dict

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_setting()
        {'jsonrpc': '2.0',
         'Timestamp': '4454.169432785',
         'method': 'get_setting',
         'result': {'temp_unit': 'C',
          'beep_volume': 'close',
          'lang': 'en',
          'center_xy': [540, 960],
          'stack_lenhance': False,
          'heater_enable': False,
          'expt_heater_enable': False,
          'focal_pos': 1580,
          'factory_focal_pos': 1580,
          'exp_ms': {'stack_l': 10000, 'continuous': 500},
          'auto_power_off': True,
          'stack_dither': {'pix': 50, 'interval': 5, 'enable': True},
          'auto_3ppa_calib': True,
          'auto_af': False,
          'frame_calib': True,
          'calib_location': 2,
          'wide_cam': False,
          'stack_after_goto': True,
          'guest_mode': False,
          'user_stack_sim': False,
          'mosaic': {'scale': 1.0,
           'angle': 0.0,
           'estimated_hours': 0.258333,
           'star_map_angle': 361.0,
           'star_map_ratio': 1.0},
          'stack': {'dbe': True, 'star_correction': True, 'cont_capt': False},
          'ae_bri_percent': 50.0,
          'manual_exp': False,
          'isp_exp_ms': -999000.0,
          'isp_gain': -9990.0,
          'isp_range_gain': [0, 400],
          'isp_range_exp_us': [30, 1000000],
          'isp_range_exp_us_scenery': [30, 1000000]},
         'code': 0,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_setting"}
    return send_command(params)


@multiple_ips
def get_user_location():
    """
    Get the Lat, Long coords of the Seestar on Earth

    Returns
    -------
    dict

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_user_location()
        {'jsonrpc': '2.0',
         'Timestamp': '4508.028353247',
         'method': 'get_user_location',
         'result': [14.7908, 47.9539],
         'code': 0,
         'id': 1}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'get_user_location'}
    return send_command(params)


@multiple_ips
def get_view_state():
    """
    Return the ``View`` dictionary from the ``iscope_get_app_state`` command

    Returns
    -------
    dict

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_view_state()
        {'jsonrpc': '2.0',
         'Timestamp': '7501.254000847',
         'method': 'get_view_state',
         'result': {'View': {'state': 'cancel',
           'lapse_ms': 282203,
           'mode': 'none',
           'cam_id': 0,
           'target_ra_dec': [9.0, 80.0],
           'target_name': 'Unknown',
           'lp_filter': False,
           'gain': 80,
           'ContinuousExposure': {'state': 'cancel',
            'lapse_ms': 116133,
            'fps': 2.024705},
           'stage': 'ContinuousExposure'}},
         'code': 0,
         'id': 1}


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_view_state"}
    return send_command(params)


@multiple_ips
def get_wheel_position():
    """
    Get the current filter-wheel position.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_wheel_position"}
    return send_command(params)


@multiple_ips
def get_wheel_setting():
    """
    Get the filter-wheel configuration settings.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "get_wheel_setting"}
    return send_command(params)


@multiple_ips
def iscope_get_app_state():
    """
        Get the full application state from the Seestar.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "iscope_get_app_state"}
    return send_command(params)


@multiple_ips
def iscope_start_view(ra=None, dec=None,
                      target_name="Unknown", lp_filter=False, mode="star",
                      mosaic=None):
    """
    Start viewing a target, but not stacking the incoming frames.

    If ``ra`` and ``dec`` are ``None``, this turns on the camera in the
    ``ContinuousExposure`` state.

    If ``ra`` and ``dec`` are defined, this triggers an ``AutoGoto`` state,
    which slews the telescope to these coordinates and then starts a plate-solve
    loop. The plate-solve loop, if successful will tell the Seestar how much
    it needs to compensate for your alignment.

    Parameters
    ----------
    ra, dec: float
        Decimal hour angle, Decimal degrees
    target_name : str
        Default: "Unknown", Name of the target, which also defines the directory
        name on the emmc drive
    lp_filter : bool
        Default: False, use the light pollution filter
    mode : str
        Default: "star", ["star", "sun", ]
    mosaic : dict, optional
        Default: None. If you want to set Seestar running on a mosaic, you need
        to provide a dict with the following keys:
        `scale`, `angle`, `star_map_angle`, `star_map_ratio`
        See below for an example


    Returns
    -------
    dict

    Examples
    --------

        >>> from seestarpy import raw
        # Put the camera into "ContinuousExposure" mode. No frames are saved.
        >>> raw.iscope_start_view()
        # Slew to a target, trigger a plate-solve, then turn the camera on.
        >>> raw.iscope_start_view(ra=13.4, dec=54.9, target_name="Mizar")

    An example for setting up mosaics, contributed by NurseJackass of the
    Seestar Collective::

        # Set up a mosaicing run and start observing
        >>> mosaic = {
        ...     'scale': 3.5,           # How many "screens" big the mosaic should be
        ...     'angle': -90,           # Rotation angle of the mosaic
        ...     'star_map_angle': 271,  # Try "361 + angle"
        ...     'star_map_ratio': 1.0,
        ... }
        >>> raw.iscope_start_view(ra=13.4, dec=54.9, target_name="Mizar", mosaic=mosaic)


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "iscope_start_view",
              "params": {"mode": mode,
                         "target_ra_dec": [ra, dec],
                         "target_name": target_name,
                         "lp_filter": lp_filter
                         }
              }
    if mosaic is not None and isinstance(mosaic, dict):
        params["params"]["mosaic"] = mosaic

    return send_command(params)


@multiple_ips
def iscope_stop_view(stage=None):
    """
    This stops whatever is happening with the Seestar.

    Parameters
    ----------
    stage : str or None
        - ``None`` (default) — set the camera mode to ``"none"``.
        - ``"ContinuousExposure"`` — turn off the camera, but leave the
          camera mode in ``"star"`` (or whatever it was).
        - ``"Stack"`` — stop stacking sub-frames but leave the camera in
          the ``ContinuousExposure`` View stage.

        Other valid stage names: ``"DarkLibrary"``, ``"AutoGoto"``,
        ``"AutoFocus"``, ``"PlateSolve"``, ``"ScopeGoto"``.

    Returns
    -------
    dict

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.iscope_stop_view("ContinuousExposure")
        {'Event': 'ContinuousExposure',
         'Timestamp': '4706.054896251',
         'state': 'cancel',
         'lapse_ms': 69217,
         'fps': 2.024333,
         'route': ['View']}

        >>> raw.iscope_stop_view("Stack")
        {'Event': 'Exposure',
         'Timestamp': '5761.848427853',
         'page': 'stack',
         'state': 'fail',
         'error': 'interrupt',
         'code': 514}

        >>> raw.iscope_stop_view(None)
        {'Event': 'View',
         'Timestamp': '721.589563996',
         'state': 'complete',
         'lapse_ms': 196484,
         'mode': 'none',
         'cam_id': 0,
         'target_ra_dec': [13.4, 54.900002],
         'target_name': 'Mizar',
         'lp_filter': False,
         'gain': 80,
         'route': []}



    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "iscope_stop_view",
              "params": {"stage": stage}}
    return send_command(params)


@multiple_ips
def iscope_start_stack(restart=False):
    """
    Start stacking sub-frames on the current target.

    Parameters
    ----------
    restart : bool, optional
        If ``True``, restart the stacking sequence. Default is ``False``.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "iscope_start_stack",
              "params": {"restart": restart}
              }
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "move_focuser",
              "params": {"step": pos,
                         "ret_step": retry}
              }
    return send_command(params)


@multiple_ips
def pi_get_time():
    """
    Get the internal system time from the device.

    .. note:: This is not always the current time, as sometimes the Seestar
       resets its internal clock on shutdown.

    Returns
    -------
    dict
        The response dictionary containing the current system time.

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.pi_get_time()

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'pi_get_time'}
    return send_command(params)


@multiple_ips
def pi_set_time(time_zone=None):
    """
    Set the internal system time on the device to the current local time.

    This function captures the current system time from the host machine and sends it to the device,
    including timezone information.

    Parameters
    ----------
    time_zone : str, optional
        The timezone to use (e.g., "Australia/Melbourne"). If not provided, it uses the
        system's local timezone.

    Returns
    -------
    dict
        The response dictionary indicating the result of the time-setting operation.

    Examples
    --------
    ::
        >>> from seestarpy import raw
        >>> raw.pi_set_time()
        >>> raw.pi_set_time("UTC")
        >>> raw.pi_set_time("Australia/Melbourne")

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    if time_zone is None:
        time_zone = get_localzone_name()

    now = datetime.now()
    print(now)
    date_json = {
        "year": now.year,
        "mon": now.month,
        "day": now.day,
        "hour": now.hour,
        "min": now.minute,
        "sec": now.second,
        "time_zone": time_zone
    }
    params = {'method': 'pi_set_time',
              'params': [date_json]}
    return send_command(params)



@multiple_ips
def pi_reboot():
    """
    Reboot the Seestar

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.pi_reboot()


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'pi_reboot'}
    return send_command(params)


@multiple_ips
def pi_shutdown(force=False):
    """
    Shutdown the Seestar. It will NOT REBOOT after shutdown!

    Parameters
    ----------
    force: bool
        Default: False. To actually force a shutdown, you need to set this to
        ``True``. This is to make sure you actually want to shut down the
        Seestar, not just reboot it.

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.pi_shutdown()
        # The previous command will do nothing. To actually shut it down:
        >>> raw.pi_shutdown(force=True)


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """

    params = {'method': 'pi_shutdown'}
    return send_command(params) if force else "Are you sure you want to shutdown? Then use force=True"


@multiple_ips
def pi_is_verified():
    """
    Check whether the device has been verified.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'pi_is_verified'}
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'pi_output_set2',
              "params": {"heater": {"state": is_dew_on,
                                    "value": dew_heater_power}
                         }
              }
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'play_sound', 'params': {"num": sound_id}}
    return send_command(params)


@multiple_ips
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

    Examples
    --------

        >>> from seestarpy import raw
        # Trigger the IMX462 chip to use Low-Conversion-Gain mode (<80)
        >>> raw.set_control_value(60)

    Notes
    -----
    High vs Low Conversion Gain modes (HCG vs LCG)

    According to the docs on the IMX462 chip, it has two internal capacitors
    which are used to read the pixel values. The larger capacitor used in the
    LCG mode can map the full pixel well depth of 32k electrons, albeit still
    only with the 12-bit ADC.
    The smaller, more sensitive capacitor used for the HCG mode, can only map
    to about a third of the full well depth. However this small capacitor
    produces less noise and is therefore much better suited for low-flux objects
    such as nebula and galaxies.

    Use cases:

    - If you prefer to map the full dynamic range of as many stars in the
      field as possible, without the bright ones "burning out" (i.e.
      saturating) then it makes sense to use the LCG mode, with gains
      set to below 80.
    - If you are looking for the best possible contrast within extended
      sources like nebulae and galaxy disks, then the HCG mode is better
      suited.  Set the gain value to 80+.


    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "set_control_value", "params": ["gain", gain]}
    return send_command(params)


@multiple_ips
def set_setting(**kwargs):
    """
    Set values in the Seestar settings dictionary.

    Should accept any of the keyword arguments returned by
    :func:`get_setting`. See the **Other Parameters** section for a full
    reference of known keys.

    Parameters
    ----------
    **kwargs
        Keyword arguments corresponding to Seestar setting keys.

    Returns
    -------
    dict

    Other Parameters
    ----------------
    temp_unit : str
        Temperature unit. One of ``'C'``, ``'F'``.
    beep_volume : str or int
        Beep volume. ``'close'`` to disable.
    lang : str
        UI language code, e.g. ``'en'``.
    center_xy : list of int
        **Not settable.** Defined by the chip size. Default ``[540, 960]``.
    stack_lenhance : bool
        Enable dark subtraction. Default ``True``.
        Needs its own call as it moves the filter.
    heater_enable : bool
        Turn on the dew heater. Default ``False``.
    expt_heater_enable : bool
        Default ``False``.
    focal_pos : int
        Current focuser position. Acceptable range [1200, 2600].
    factory_focal_pos : int
        Factory default focuser position (1580).
    expert_mode : bool
        Allow exposure times of 2 s and 5 s via ``exp_ms``. Default ``False``.
    exp_ms : dict
        Exposure times in milliseconds.
        Keys: ``'stack_l'`` (stacking, accepts 10/20/30/60 s; also 2/5 s
        with ``expert_mode=True``), ``'continuous'`` (live view).
    auto_power_off : bool
        Auto power-off after ~15 min of inactivity. Default ``True``.
    stack_dither : dict
        Dither settings: ``'pix'`` (throw in pixels), ``'interval'``
        (frames between dithers), ``'enable'`` (bool).
    auto_3ppa_calib : bool
        Automatic 3-point polar-alignment calibration. Default ``True``.
    auto_af : bool
        Auto-focus after a goto. Default ``False``.
    frame_calib : bool
        Default ``True``.
    calib_location : int
        Default ``2``.
    preview : dict
        **Firmware 8.46+ only.** Image- and video-stream transport
        settings. Keys: ``'image_transfer_mode'`` (``'Jpg'`` or
        ``'Raw'`` — see :func:`set_image_transfer_mode`),
        ``'rtsp_quality'`` (``'HighQuality'`` or ``'Smooth'``),
        ``'rtsp_width'``, ``'rtsp_height'``. Absent on earlier firmware,
        which always sends ``Raw``.
    wide_cam : bool
        Use the wide-field camera (S30pro). Default ``False``.
    wide_4k : bool
        Stack using the 4k dither approach. Default ``True``.
    stack_after_goto : bool
        Start stacking automatically after goto (firmware 2.1+).
        Default ``True``.
    guest_mode : bool
        Default ``False``.
    user_stack_sim : bool
        Default ``False``.
    mosaic : dict
        Mosaic settings: ``'scale'``, ``'angle'``, ``'estimated_hours'``,
        ``'star_map_angle'``, ``'star_map_ratio'``.
    stack : dict
        Stacking settings: ``'dbe'``, ``'star_correction'``,
        ``'cont_capt'`` (``True`` to save every frame without stacking),
        ``'drizzle2x'`` (create 4k image by debayering and drizzling),
        ``'airplane_line_removal'``, ``'wide_denoise'``,
        ``'capt_type'``, ``'save_discrete_frame'``,
        ``'save_discrete_ok_frame'``, ``'capt_num'``,
        ``'light_duration_min'``, ``'brightness'``, ``'contrast'``,
        ``'saturation'``, ``'dbe_enable'``.
    ae_bri_percent : float
        Default ``50.0``.
    manual_exp : bool
        Default ``False``.
    isp_exp_ms : float
        Default ``-999000.0``.
    isp_gain : float
        Default ``-9990.0``.
    isp_range_gain : list
        Default ``[0, 400]``.
    isp_range_exp_us : list
        Default ``[30, 1000000]``.
    isp_range_exp_us_scenery : list
        Default ``[30, 1000000]``.
    wifi_country : str or None
        Default ``None``.
    usb_en_eth : bool
        Default ``False``.
    dark_mode : bool
        Default ``False``.
    plan_target_af : bool
        Auto-focus between planned observations. Default ``False``.
    viewplan_gohome : bool
        Default ``True``.
    remote_joined : bool
        Whether the Seestar is connected via a remote connection.
        Default ``False``.

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.set_setting(exp_ms={"stack_l": 20000})
        >>> raw.set_setting(stack_dither={"pix": 50, "interval": 5, "enable": True})

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "set_setting", "params": kwargs}
    return send_command(params)


#: Accepted ``image_transfer_mode`` values, keyed by the friendly aliases
#: :func:`set_image_transfer_mode` understands.  The firmware itself takes
#: only ``'Jpg'`` and ``'Raw'`` (the ``StackImageQuality`` enum in the app).
_TRANSFER_MODE_ALIASES = {
    "jpg": "Jpg", "jpeg": "Jpg", "compressed": "Jpg",
    "raw": "Raw", "lossless": "Raw", "full": "Raw",
}


@multiple_ips
def get_preview_setting():
    """
    Read the image-stream preview settings (firmware 8.46+).

    Firmware 8.46 added a ``preview`` block to :func:`get_setting`,
    controlling how frames are sent over the binary image ports
    (4800/4804) and the RTSP video ports:

    - ``image_transfer_mode`` — ``'Jpg'`` or ``'Raw'``.  See
      :func:`set_image_transfer_mode`; this is the setting that decides
      whether a stacked frame costs 2.5 MB or 50 MB.
    - ``rtsp_quality`` — ``'HighQuality'`` or ``'Smooth'``.
    - ``rtsp_width`` / ``rtsp_height`` — video stream dimensions.

    Returns
    -------
    dict or None
        The preview block, or ``None`` on firmware that predates it
        (7.75 and earlier have no such setting and always send ``Raw``).

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_preview_setting()
        {'rtsp_quality': 'HighQuality', 'image_transfer_mode': 'Jpg',
         'rtsp_width': 1080, 'rtsp_height': 1920}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return (send_command({"method": "get_setting"})
            .get("result", {})
            .get("preview"))


@multiple_ips
def set_image_transfer_mode(mode):
    """
    Choose how stacked images cross the wire (firmware 8.46+).

    The binary image stream can deliver a stacked frame two ways, and
    the difference is not small — measured on an 8 MP S30 Pro over
    Wi-Fi:

    ==========  ============  ==========  ==================================
    mode        frame size    time        what you get
    ==========  ============  ==========  ==================================
    ``'Jpg'``   ~2.5 MB       ~5 s        a finished, firmware-stretched
                                          JPEG (``img_type`` 4)
    ``'Raw'``   ~50 MB        ~30 s       linear 16-bit RGB you stretch
                                          yourself (``img_type`` 5)
    ==========  ============  ==========  ==================================

    ``'Jpg'`` is the right choice for monitoring — a dashboard, a live
    view, anything that just wants to see the frame.  Keep ``'Raw'`` when
    you need the linear data for your own processing; the JPEG has
    already been tone-mapped and cannot be undone.

    :func:`seestarpy.stream.decode_payload` handles both, so nothing
    downstream has to care which is in force.

    Parameters
    ----------
    mode : str
        ``'Jpg'`` or ``'Raw'``.  The aliases ``'jpeg'``, ``'compressed'``,
        ``'lossless'`` and ``'full'`` are also accepted, case-insensitively.

    Returns
    -------
    dict
        The ``set_setting`` response.

    Raises
    ------
    ValueError
        If *mode* is not a recognised value.  Checked before the
        round-trip, because the firmware answers an unknown value with a
        bare error code.

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.set_image_transfer_mode("Jpg")
        >>> raw.set_image_transfer_mode("raw", ips="all")

    Notes
    -----
    This is a **persistent device setting**, shared with the phone app —
    it is not scoped to your connection.  Firmware earlier than 8.46 has
    no ``preview`` block and always sends ``Raw``; setting it there has
    no effect.

    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    key = _TRANSFER_MODE_ALIASES.get(str(mode).strip().lower())
    if key is None:
        raise ValueError(
            f"Unknown image transfer mode {mode!r}. "
            f"Use 'Jpg' or 'Raw' (aliases: "
            f"{sorted(_TRANSFER_MODE_ALIASES)})."
        )
    return send_command({"method": "set_setting",
                         "params": {"preview": {"image_transfer_mode": key}}})


#: Accepted ``typec_mode`` values, keyed by the friendly aliases accepted by
#: :func:`set_usb_mode`.  The firmware itself only accepts ``'file'`` and
#: ``'net'`` (anything else returns error 102).
_USB_MODE_ALIASES = {
    "file": "file", "drive": "file", "storage": "file", "usb": "file",
    "net": "net", "eth": "net", "ethernet": "net", "lan": "net",
}


@multiple_ips
def get_usb_mode():
    """
    Report how the USB-C port is currently configured.

    Reads the two settings that govern the USB-C port role: ``typec_mode``
    (``'file'`` = mass-storage drive, ``'net'`` = wired Ethernet) and
    ``usb_en_eth`` (master switch for USB Ethernet).

    Returns
    -------
    dict
        ``{'typec_mode': str, 'usb_en_eth': bool}``.

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_usb_mode()
        {'typec_mode': 'file', 'usb_en_eth': False}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    # send_command() rather than get_setting(): a nested @multiple_ips call
    # re-validates the inherited IP against connection.AVAILABLE_IPS, which
    # only ever holds the address discovered at import time, so any other
    # scope resolves to an empty target list.
    result = send_command({"method": "get_setting"})["result"]
    return {"typec_mode": result.get("typec_mode"),
            "usb_en_eth": result.get("usb_en_eth")}


@multiple_ips
def set_usb_mode(mode):
    """
    Switch the USB-C port between mass-storage and wired-LAN modes.

    The Seestar's USB-C port is dual-role:

    - ``'file'`` — the scope presents itself as a USB mass-storage
      **device**, i.e. it mounts as a drive when plugged into a computer.
      This also switches ``usb_en_eth`` back off.
    - ``'net'`` — the scope becomes a USB **host** that drives an external
      USB-to-Ethernet adapter, putting it on a wired LAN.  This also
      switches ``usb_en_eth`` on.

    Both modes write ``usb_en_eth`` and ``typec_mode`` together, so the two
    calls are exact reversals of each other.  The firmware does not couple
    them: writing ``typec_mode`` alone leaves ``usb_en_eth`` at whatever it
    was.

    Parameters
    ----------
    mode : str
        ``'file'`` (aliases ``'drive'``, ``'storage'``, ``'usb'``) or
        ``'net'`` (aliases ``'eth'``, ``'ethernet'``, ``'lan'``).

    Returns
    -------
    dict
        The ``set_setting`` response.

    Raises
    ------
    ValueError
        If *mode* is not one of the accepted values/aliases.

    Notes
    -----
    Only ``typec_mode`` values ``'file'`` and ``'net'`` are valid; the
    firmware rejects anything else with error 102.

    Switching modes restarts the scope's USB subsystem, so the port goes
    away and comes back — expect a few seconds before it settles, and any
    mounted drive to disappear the moment you select ``'net'``.  On an S50
    running fw 8.46 the role change re-negotiated over an already-seated
    cable with no replug needed (the mass-storage gadget re-enumerated on
    its own within seconds), and the scope's Wi-Fi connection was not
    disturbed.  Other firmware/host combinations may still need a physical
    **unplug and re-plug** before the drive reappears.

    ``pi_status.is_typec_connected`` tracks the mass-storage gadget, not
    the wired LAN: it reads ``True`` in ``'file'`` mode and flips to
    ``False`` in ``'net'`` mode, even while the port is powered.

    Getting onto a wired LAN also needs a powered USB-C-to-Ethernet
    adapter (with PD) between the scope and the router; ``'net'`` mode
    alone only arms the firmware.

    Accepts the ``ips`` keyword for multi-Seestar operation.

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.set_usb_mode("net")     # arm the scope for a wired LAN
        >>> raw.set_usb_mode("file")    # present the scope as a USB drive
    """
    key = _USB_MODE_ALIASES.get(str(mode).lower())
    if key is None:
        raise ValueError(
            f"Unknown USB mode {mode!r}. Use 'file' (mass-storage drive) "
            f"or 'net' (wired Ethernet)."
        )
    # Always write both keys, so each mode is a true reversal of the other:
    # setting ``typec_mode`` on its own leaves ``usb_en_eth`` latched at its
    # previous value (confirmed on an S50 running fw 8.46).  send_command()
    # rather than set_setting() for the nesting reason in get_usb_mode().
    return send_command({"method": "set_setting",
                         "params": {"usb_en_eth": key == "net",
                                    "typec_mode": key}})


@multiple_ips
def _get_link_type_by_ip():
    """Per-IP implementation backing :func:`get_link_type`.

    Kept separate so :func:`get_link_type` can remap the ``@multiple_ips``
    aggregate dict (keyed by IP) to be keyed by serial number instead.
    """
    ip = current_ip()
    state = send_command({"method": "get_device_state",
                          "params": {"keys": ["station", "device"]}})["result"]
    station_ip = state.get("station", {}).get("ip")
    sn = state.get("device", {}).get("sn")
    setting = send_command({"method": "get_setting"})["result"]

    if station_ip is None:
        link = "unknown"
    elif station_ip == ip:
        link = "wifi"
    else:
        link = "wired"

    return {"sn": sn, "link": link, "ip": ip, "station_ip": station_ip,
            "typec_mode": setting.get("typec_mode"),
            "usb_en_eth": setting.get("usb_en_eth")}


def get_link_type(ips=None):
    """
    Determine whether each Seestar is currently reachable over Wi-Fi or a
    wired USB-Ethernet gadget.

    The firmware has no single field for "which NIC is this connection
    actually using", so this infers it by comparing the IP the command
    was sent to against the IP the Wi-Fi station interface reports for
    itself (``get_device_state()["station"]["ip"]``):

    - If they **match**, the connection is going over Wi-Fi.
    - If they **differ**, the Wi-Fi radio is associated to its AP but
      idle for this connection — traffic must be going over the wired
      USB-Ethernet gadget instead (see :func:`get_usb_mode`).

    Parameters
    ----------
    ips
        See the ``ips`` keyword accepted by every function in this module
        (an IP/hostname, an int, ``"all"``, a list, or ``None`` for
        :data:`~seestarpy.connection.DEFAULT_IP`).

    Returns
    -------
    dict
        Keyed by each Seestar's serial number (falling back to its IP if
        the serial can't be read), with values
        ``{'link': 'wifi' | 'wired' | 'unknown', 'ip': str,
        'station_ip': str or None, 'typec_mode': str or None,
        'usb_en_eth': bool or None}``.  ``'unknown'`` only occurs if the
        Wi-Fi station block is absent (e.g. Wi-Fi never configured).

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.get_link_type(ips="all")
        {'97783b61': {'link': 'wired', 'ip': '192.168.1.55',
                      'station_ip': '192.168.1.83',
                      'typec_mode': 'net', 'usb_en_eth': True},
         'ce545589': {'link': 'wifi', 'ip': '192.168.1.106',
                      'station_ip': '192.168.1.106',
                      'typec_mode': 'file', 'usb_en_eth': False}}

    Notes
    -----
    Fetches ``station``/``device`` via :func:`send_command` directly
    rather than :func:`get_device_state` / :func:`get_usb_mode`, to avoid
    the nested-``@multiple_ips`` IP-resolution pitfall described in
    :func:`get_usb_mode`.
    """
    result = _get_link_type_by_ip(ips=ips)
    if "link" in result:
        return result
    return {v.get("sn") or k: v for k, v in result.items()}


@multiple_ips
def get_sequence_setting():
    """
    Read the sequence (observation group) settings.

    The ``group_name`` in the reply is the target name the current
    observation sequence is filing frames under — see
    :func:`seestarpy.status.get_target_name` for just that field.

    Returns
    -------
    dict
        ``result`` carries ``group_name``, the ``delay_first`` /
        ``delay_between_frame`` pacing, and the end-of-sequence flags
        (``park_mount``, ``shutdown_pi``, ``close_cooler``).

    Examples
    --------
    ::

        >>> from seestarpy import raw
        >>> raw.get_sequence_setting()["result"]
        {'delay_first': 0, 'delay_between_frame': 0, 'group_by_slot': True,
         'merid_flip': False, 'group_name': 'M 81', 'park_mount': False,
         'shutdown_pi': False, 'close_cooler': False, 'left_size_m': 0.0,
         'left_time_sec': 0}

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "get_sequence_setting"})


@multiple_ips
def set_sequence_setting(name):
    """
    Set the sequence (observation group) name.

    Parameters
    ----------
    name : str
        The group name for the observation sequence.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "set_sequence_setting",
              "params": [{"group_name": name}]}
    return send_command(params)


@multiple_ips
def set_sensor_calibration(x, y, z, x11, x12, y11, y12):
    """
    Override device's compass bearing to account for the magnetic declination 
    at device's position.
    
    Parameters
    ----------
    x, y, z : float
        Compass sensor offsets.
    x11, x12, y11, y12 : float
        Rotation matrix coefficients.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
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


@multiple_ips
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

    Examples
    --------

        >>> from seestarpy import raw
        >>> raw.set_user_location(48.2, 16.4)   # For Vienna, Austria


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'set_user_location',
              'params': {'lat': lat,
                         'lon': lon,
                         'force': True}}
    return send_command(params)


@multiple_ips
def set_wheel_position(pos):
    """
    Set the filter-wheel position.

    Parameters
    ----------
    pos : int
        - 0: Dark (shutter closed)
        - 1: Open (400--700 nm, with Bayer RGB matrix)
        - 2: Narrow (30 nm OIII + 20 nm Ha, also LP filter)

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "set_wheel_position", "params": [pos]}
    return send_command(params)


@multiple_ips
def scope_get_equ_coord():
    """
    Get the current equatorial coordinates (RA/Dec) from the mount.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_get_equ_coord'}
    return send_command(params)


@multiple_ips
def scope_get_horiz_coord():
    """
    Get the current horizontal coordinates (Alt/Az) from the mount.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_get_horiz_coord'}
    return send_command(params)


@multiple_ips
def scope_get_ra_dec():
    """
    Get the current RA/Dec coordinates from the mount.

    .. note:: Requires firmware v6.70 or later.

    .. warning::
        **Prefer** :func:`scope_get_equ_coord`.  It is the RA/Dec getter the
        official app uses on the command socket on every firmware, and it
        answers with a ``dict``.  This method is primarily the *image-stream*
        (port 4800) heartbeat, and on the command socket it returns a
        **three-element list**, so the two are not drop-in replacements for
        one another:

        .. code-block:: python

            raw.scope_get_ra_dec()["result"]      # [7.152778, -47.754167, 19.154327]
            raw.scope_get_equ_coord()["result"]   # {'ra': 7.152778, 'dec': -47.754167}

        The third element appears to be local sidereal time.

        The wrapper falls back to ``scope_get_equ_coord`` if the firmware
        answers ``code 103`` ("method not found"), which means the return
        *shape* depends on which path ran — another reason to call
        :func:`scope_get_equ_coord` directly.  Note this fallback has not
        been observed to trigger: measured live on firmware **8.46 and
        8.89**, ``scope_get_ra_dec`` is accepted on the command socket
        (``code 0``).  An earlier version of this docstring stated that v8.x
        rejects it; that was wrong — the incompatibility is the changed
        return shape, not availability.

    Returns
    -------
    dict
        ``result`` is a list ``[ra_hours, dec_deg, lst_hours]``, or the dict
        from :func:`scope_get_equ_coord` if the fallback fired.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    resp = send_command({'method': 'scope_get_ra_dec'})
    if isinstance(resp, dict) and resp.get("code") == 103:
        return send_command({'method': 'scope_get_equ_coord'})
    return resp


@multiple_ips
def scope_get_track_state():
    """
    Get the current tracking state of the mount.

    .. note:: Requires firmware v6.70 or later.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_get_track_state'}
    return send_command(params)


@multiple_ips
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
        {'Event': 'ScopeGoto',
         'Timestamp': '6880.953156944',
         'state': 'working',
         'lapse_ms': 0}


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_goto', 'params': [ra, dec]}
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    The wire method and (empty) params are **unchanged** across firmware —
    ``scope_move_to_horizon`` is still present in the v8.30-era app command
    set and takes no params, so this call is correct on modern firmware.  If
    it appears to "fail", inspect the returned dict's ``code``/``error``: the
    usual cause is a **precondition** — the scope must be awake/initialised
    (not mid-park, not already slewing) before it will honour the move.

    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_move_to_horizon'}
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_park',
              "params": {"equ_mode": set_eq_mode}}
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_set_track_state', "params": flag}
    return send_command(params)


@multiple_ips
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


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'scope_sync', "params": [in_ra, in_dec]}
    return send_command(params)


@multiple_ips
def scope_speed_move(angle, speed, dur_sec):
    """
    Moves the scope as if using a joy-stick to control the movement.

    This method moves both Base- and Arm-motors as if the user is controlling
    the seestar with a joystick.

    Notes regarding the angle argument:
    - 0: Move right (Base motor) relative to where the Seestar is pointing.
    - 90: Move up (Arm motor)
    - 180: Move left (Base motor)
    - 270: Move down (Arm motor)
    Any other angle between the cardinal points engages both Base- and Arm-motors,
    with the speed of each individual motor throttled by the sin and cos of
    the angle.

    Notes regarding the speed argument:
    Max 1500. Step-size: 15 arcseconds.
    Speed = 240 delivers 1 deg/sec
    NOTE: This is the absolute speed of both motors. The individual speed
    of each of the Base and Arm motors is `speed * cos/sin(angle)`.
    This step-size translates to:
    - Base motor: RA (Hour Angle)  RA=00h00m01s per step
    - Arm motor: Dec (Declination) Dec=00d00m15s per step

    Parameters
    ----------
    angle: int
        [deg] Angle on a circle of a joystick for controlling the two motors

    speed: int
        [Steps per second] Combined speed of the two motors. Max = 1500.
        1 step = 15 arcseconds.

    dur_sec: int
        [sec] Time for moving the scope arm. Max = 10 sec

    Returns
    -------
    dict

    Examples
    --------
    ::
        >>> from seestarpy import raw
        # Move left at full speed for 10 seconds
        >>> raw.scope_speed_move(speed=1500, angle=180, dur_sec=10)
        # Move up at 1 deg/sec for 2 seconds = 2 deg up
        >>> raw.scope_speed_move(speed=240, angle=270, dur_sec=2)   # Move down
        # Move up and right at 2 deg/sec for 5 seconds.
        # Az (Base-motor) speed is 1.72 deg/sec and Alt (Arm-motor) speed is 1 deg/sec
        >>> raw.scope_speed_move(speed=480, angle=30, dur_sec=5)   # Move down


    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "scope_speed_move",
              "params": {"speed": speed, "angle": angle, "dur_sec": dur_sec}}
    return send_command(params)


@multiple_ips
def start_auto_focuse():
    """
    Start the auto-focus routine.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "start_auto_focuse"}
    return send_command(params)


@multiple_ips
def start_create_dark():
    """
    Start creating a dark-frame library.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "start_create_dark"}
    return send_command(params)


@multiple_ips
def start_polar_align(restart=True, dec_pos_index=3):
    """
    Run the three-point polar-alignment (3PPA) sequence.

    The scope must be in EQ mode (``mount.equ_mode`` true).  It may be
    EQ-parked (``mount.close`` true, reporting ``dec = -90`` and
    ``alt = -latitude``) or already deployed; the firmware slews to the
    first alignment point itself, which takes ~45 s from parked and
    ~10 s from deployed.  No ``scope_goto`` is needed — and none is sent
    by the phone app.

    .. warning::
       The firmware ties the alignment to the TCP connection that issued
       this command, and closes an idle port-4700 socket after ~15.5 s.
       Calling this bare therefore gets the alignment cancelled ~19 s in,
       leaving the mount stopped mid-slew — which looks like a partial
       ~90 deg rotation when started from parked, or like a hang after
       one movement when started from deployed.  Both are the same
       abort.  Use :func:`~seestarpy.ui.polar_align`, which holds the
       connection open, or wrap this call in
       :class:`~seestarpy.connection.keepalive` yourself.

    Parameters
    ----------
    restart : bool, optional
        ``True`` (default) runs the whole three-point sequence: slew,
        solve, rotate, solve, rotate, solve, then report the error.
        ``False`` re-measures at the current position without moving the
        DEC arm — a single plate-solve producing ``3PPA`` ``calc4``
        (``state_code`` 17), used to check the residual after physically
        adjusting the tripod.  *dec_pos_index* is then omitted from the
        payload, matching the phone app.
    dec_pos_index : int or None, optional
        DEC band to align on, as offered by the app's pitch picker.
        The arc is centred on ``dec = latitude + 30 * (index - 3)``, so
        the default ``3`` puts it overhead at ``dec = latitude`` and each
        step is 30 deg.  Measured on a 47.95 deg site: ``2`` -> 17.95,
        ``3`` -> 47.95, ``4`` -> 77.95.  Pick a band clear of
        obstructions.  Only sent when *restart* is ``True``; pass
        ``None`` to omit it entirely.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.

    Progress arrives as ``EqModePA`` and ``3PPA`` events on port 4700.
    The ``3PPA`` ``state_code`` ladder is ``1`` start, ``5`` move1,
    ``6`` delay1, ``10`` move2, ``11`` delay2, ``14`` calc3, ``17``
    calc4; the ``calc*`` states carry a ``pa_error`` block, and
    ``EqModePA`` ``complete`` repeats the final ``total``/``x``/``y``.
    ``x`` is the azimuth error and ``y`` the altitude error of the
    *mount*, in degrees — correct the tripod by the same amount in the
    opposite direction.  Each of the two rotations sweeps ~21.5 deg in
    RA, so the three solves span ~43 deg.

    Examples
    --------

        >>> import seestarpy as ssp
        >>> ssp.set_eq_mode(True)               # park into EQ mode
        >>> ssp.polar_align()                   # preferred: blocks, keepalive
        >>> ssp.polar_align(restart=False)      # re-check after adjusting

    """
    inner = {"restart": bool(restart)}
    # The app only ever sends dec_pos_index alongside restart=True; on a
    # continue it drops the key rather than sending a stale index.
    if restart and dec_pos_index is not None:
        inner["dec_pos_index"] = int(dec_pos_index)
    params = {"method": "start_polar_align", "params": inner}
    return send_command(params)


@multiple_ips
def start_scan_planet():
    """
    Start scanning for planets.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "start_scan_planet"}
    return send_command(params)


@multiple_ips
def start_solve():
    """
    Start a plate-solve on the current field.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "start_solve"}
    return send_command(params)


@multiple_ips
def stop_auto_focuse():
    """
    Stop the auto-focus routine.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "stop_auto_focuse"}
    return send_command(params)


@multiple_ips
def stop_create_dark():
    """
    Stop dark-frame library creation.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "stop_create_dark"}
    return send_command(params)


@multiple_ips
def stop_polar_align():
    """
    Stop the polar-alignment sequence.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "stop_polar_align"}
    return send_command(params)


@multiple_ips
def stop_solve():
    """
    Stop the current plate-solve.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {"method": "stop_solve"}
    return send_command(params)


@multiple_ips
def test_connection():
    """
    Test the connection to the Seestar.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    params = {'method': 'test_connection'}
    return send_command(params)


@multiple_ips
def random_command(method, params=None):
    """
    Send an arbitrary command to the Seestar.

    Parameters
    ----------
    method : str
        The JSON-RPC method name.
    params : dict, optional
        Parameters to pass with the command.

    Returns
    -------
    dict or str

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": method, "params": params})