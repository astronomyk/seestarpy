from datetime import datetime

from src.seestarpy.connection import send_command


def set_time():
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


def get_time():
    params = {'method': 'pi_get_time'}
    return send_command(params)


def test_connection():
    params = {'method': 'test_connection'}
    return send_command(params)


def get_user_location():
    params = {'method': 'get_user_location'}
    return send_command(params)


def set_user_location(lat, lon):
    params = {'method': 'set_user_location', 'params': {'lat': lat, 'lon': lon, 'force': True}}
    return send_command(params)


def start_polar_align():
    params = {"method": "start_polar_align"}
    return send_command(params)


def stop_polar_align():
    params = {"method": "stop_polar_align"}
    return send_command(params)


def get_plate_solve_result():
    params = {"method": "get_solve_result"}
    return send_command(params)


def start_plate_solve():
    params = {"method": "start_solve"}
    return send_command(params)
