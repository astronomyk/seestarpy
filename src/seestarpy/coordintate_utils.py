import math
import datetime

def ra_dec_to_alt_az(ra_hours, dec_deg, lat_deg, lon_deg, timestamp=None):
    """
    Convert Right Ascension and Declination to Altitude and Azimuth.
    All angles in degrees. RA in hours.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.UTC)

    # Convert RA from hours to degrees
    ra_deg = ra_hours * 15.0

    # Compute Julian Date
    JD = timestamp.timestamp() / 86400.0 + 2440587.5
    D = JD - 2451545.0

    # Mean Sidereal Time in degrees
    GMST = 280.46061837 + 360.98564736629 * D
    GMST = GMST % 360

    # Local Sidereal Time
    LST = GMST + lon_deg
    LST = LST % 360

    # Hour Angle
    HA = LST - ra_deg
    HA = HA % 360
    if HA > 180:
        HA -= 360  # convert to [-180, 180] range

    # Convert to radians
    HA_rad = math.radians(HA)
    dec_rad = math.radians(dec_deg)
    lat_rad = math.radians(lat_deg)

    # Calculate Altitude
    sin_alt = math.sin(dec_rad) * math.sin(lat_rad) + math.cos(dec_rad) * math.cos(lat_rad) * math.cos(HA_rad)
    alt_rad = math.asin(sin_alt)

    # Calculate Azimuth
    cos_az = (math.sin(dec_rad) - math.sin(alt_rad) * math.sin(lat_rad)) / (math.cos(alt_rad) * math.cos(lat_rad))
    cos_az = min(1.0, max(-1.0, cos_az))  # clamp to valid range
    az_rad = math.acos(cos_az)

    # Determine azimuth direction
    if math.sin(HA_rad) > 0:
        az_rad = 2 * math.pi - az_rad

    alt_deg = math.degrees(alt_rad)
    az_deg = math.degrees(az_rad)

    return alt_deg, az_deg

def get_mount_alt_az_from_latest_state(state):
    try:
        equ_coord = state.get("scope_get_equ_coord", {}).get("result", {})
        device_state = state.get("get_device_state", {}).get("result", {})
        ra = equ_coord.get("ra")
        dec = equ_coord.get("dec")
        lon, lat = device_state.get("location_lon_lat", [None, None])

        if None in (ra, dec, lat, lon):
            return None, None

        return ra_dec_to_alt_az(ra, dec, lat, lon)

    except Exception as e:
        print("[coord error]", e)
        return None, None
