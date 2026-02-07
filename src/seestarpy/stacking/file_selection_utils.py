from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List, Union, Dict, Tuple, Iterable

from astropy.io import fits


_TS_RE = re.compile(r'(\d{8})-(\d{6})')  # YYYYMMDD-HHMMSS

def _dt_from_filename_utc(filename: str) -> datetime:
    """
    Extract UTC datetime from filenames containing 'YYYYMMDD-HHMMSS'.
    """
    m = _TS_RE.search(filename)
    if not m:
        raise ValueError(f"No YYYYMMDD-HHMMSS timestamp found in filename: {filename}")
    ymd, hms = m.groups()
    return datetime.strptime(ymd + hms, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def group_filenames_by_15min_chunk_ymd(filenames: Iterable[str],) -> Dict[str, List[str]]:
    """
    Group filenames into 15-minute UTC chunks.

    Key format:
        YYYYMMDD-CC

    where:
      - YYYYMMDD is the UTC calendar date
      - CC is the 15-minute chunk number within that day (0..95)
    """
    buckets: Dict[str, List[tuple[datetime, str]]] = {}

    for fn in filenames:
        dt = _dt_from_filename_utc(fn)

        # UTC calendar date
        ymd = dt.strftime("%Y%m%d")

        # Seconds since UTC midnight
        seconds_into_day = (
            dt.hour * 3600
            + dt.minute * 60
            + dt.second
            + dt.microsecond / 1e6
        )

        # 15-minute chunk index
        cc = int(seconds_into_day // 900)  # 900 = 15 * 60
        if not (0 <= cc <= 95):
            raise RuntimeError(f"Computed CC out of range for {fn}: {cc}")

        key = f"{ymd}-{cc:02d}"
        buckets.setdefault(key, []).append((dt, fn))

    # Sort filenames within each chunk by timestamp
    out: Dict[str, List[str]] = {}
    for key, items in buckets.items():
        items.sort(key=lambda x: x[0])
        out[key] = [fn for _, fn in items]

    # Optional: sort keys chronologically
    return dict(sorted(out.items()))

def _fmt_pointing(ra_deg: float, dec_deg: float) -> str:
    """
    Format pointing coords as 'RRR.RR+DD.DD' (or 'RRR.RR-DD.DD').
    """
    ra_s = f"{ra_deg % 360.0:06.2f}"   # normalize RA into [0, 360)
    sign = "+" if dec_deg >= 0 else "-"
    dec_s = f"{abs(dec_deg):05.2f}"
    return f"{ra_s}{sign}{dec_s}"


def _read_ra_dec_from_header(hdr) -> Tuple[float, float]:
    """
    Extract RA/Dec (decimal degrees) from FITS header keys 'RA' and 'DEC'.
    """
    try:
        ra_deg = float(hdr["RA"])
        dec_deg = float(hdr["DEC"])
    except KeyError as e:
        raise KeyError("FITS header must contain 'RA' and 'DEC'") from e

    return ra_deg, dec_deg


def group_files_by_pointing_coords(
    fnames: List[str],
) -> Union[List[str], List[List[str]]]:
    """
    Read FITS headers, build pointing strings 'RRR.RR+DD.DD',
    and group files by pointing.

    Returns:
      - original `fnames` if only one unique pointing exists
      - otherwise: list of lists, one per unique pointing
    """
    groups: Dict[str, List[str]] = {}

    for fn in fnames:
        hdr = fits.getheader(fn)  # header only
        ra_deg, dec_deg = _read_ra_dec_from_header(hdr)
        key = _fmt_pointing(ra_deg, dec_deg)
        groups.setdefault(key, []).append(fn)

    return groups

