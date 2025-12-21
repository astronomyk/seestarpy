from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List, Union, Dict, Tuple, Iterable, Optional, Literal

from astropy.io import fits
import numpy as np
import astroalign as aa
import sep


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


def extract_starlists_from_fits_group(
    fnames: List[str],
    *,
    detection_sigma: float = 3.0,
    min_area: int = 5,
    max_sources: int = 300,
    subtract_background: bool = True,
    return_flux: bool = False,
) -> Dict[str, np.ndarray]:
    """
    Extract a star-list from each FITS image in `fnames` using SEP.

    Parameters
    ----------
    fnames
        List of FITS filenames.

    detection_sigma
        Detection threshold in units of the (global) background RMS.

    min_area
        Minimum number of connected pixels for a detection.

    max_sources
        Keep only the brightest `max_sources` detections (by flux).

    subtract_background
        If True, estimates + subtracts background before extraction.

    return_flux
        If False (default): returns Nx2 arrays of (x, y).
        If True: returns Nx3 arrays of (x, y, flux).

    Returns
    -------
    starlists
        Dict mapping filename -> array of detected sources.
        Array shape:
          - (N, 2) for (x, y) if return_flux=False
          - (N, 3) for (x, y, flux) if return_flux=True

    Notes
    -----
    - Coordinates are pixel coordinates in SEP convention: x increases to the right,
      y increases downward, and (0,0) is the first pixel.
    - This function only extracts sources; it does *not* do any alignment.
    """
    starlists: Dict[str, np.ndarray] = {}

    for fn in fnames:
        img = np.asarray(fits.getdata(fn), dtype=np.float32, order="C")

        if subtract_background:
            bkg = sep.Background(img)
            data = img - bkg
            thresh = detection_sigma * bkg.globalrms
        else:
            data = img
            # Fallback threshold estimate if not subtracting background
            thresh = detection_sigma * float(np.nanstd(data))

        objs = sep.extract(data, thresh, minarea=min_area)

        if objs.size == 0:
            # Store an empty array (so you can decide what to do later)
            starlists[fn] = np.empty((0, 3 if return_flux else 2), dtype=np.float32)
            continue

        # Sort by flux descending and keep the brightest detections
        order = np.argsort(objs["flux"])[::-1]
        objs = objs[order[:max_sources]]

        if return_flux:
            arr = np.vstack([objs["x"], objs["y"], objs["flux"]]).T.astype(np.float32)
        else:
            arr = np.vstack([objs["x"], objs["y"]]).T.astype(np.float32)

        starlists[fn] = arr

    return starlists


def find_transforms_to_reference(
    starlists_xy: Dict[str, np.ndarray],
    reference_fname: str,
    *,
    max_control_points: int = 50,
) -> Dict[str, aa.AffineTransform]:
    """
    Given per-file star lists (Nx2 arrays), compute astroalign transforms
    that map each file's coordinates -> reference coordinates.

    Returns dict: filename -> transform (reference maps to itself as None).
    """
    if reference_fname not in starlists_xy:
        raise KeyError("reference_fname not found in starlists_xy")

    ref_xy = starlists_xy[reference_fname]
    if ref_xy.shape[0] == 0:
        raise ValueError("Reference star list is empty")

    transforms: Dict[str, aa.AffineTransform] = {}

    for fn, xy in starlists_xy.items():
        if fn == reference_fname:
            continue
        if xy.shape[0] == 0:
            continue

        transform, _matches = aa.find_transform(
            xy, ref_xy, max_control_points=max_control_points
        )
        transforms[fn] = transform

    return transforms


def apply_transforms_and_stack(
    fnames: List[str],
    reference_fname: str,
    transforms: Dict[str, aa.AffineTransform],
    *,
    combine: Literal["median", "mean"] = "median",
    sigma_clip: Optional[float] = None,
    fill_value: float = np.nan,
    skip_missing_transform: bool = True,
    return_aligned: bool = False,
) -> np.ndarray | Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Apply precomputed astroalign transforms to a set of FITS files, align them to a chosen
    reference frame, and optionally stack.

    Parameters
    ----------
    fnames
        Filenames to process (order matters only for returned aligned dict if requested).

    reference_fname
        The filename that defines the reference pixel grid. This frame is included unmodified.

    transforms
        Dict: filename -> astroalign transform mapping (filename coords) -> (reference coords).
        Typically produced by aa.find_transform(xy, ref_xy).

    combine
        "median" (default) or "mean".

    sigma_clip
        Optional per-pixel sigma clipping threshold applied before combining.

    fill_value
        Fill value outside transformed footprint.

    skip_missing_transform
        If True, frames without a transform are skipped. If False, raises KeyError.

    return_aligned
        If True, also return dict mapping filename -> aligned image (float32).

    Returns
    -------
    stacked
        2D stacked image (float32).

    (optional) aligned_images
        Dict: filename -> aligned image (float32). Includes the reference frame.
    """
    if not fnames:
        raise ValueError("fnames is empty")
    if reference_fname not in fnames:
        raise ValueError("reference_fname must be present in fnames")

    # Load reference image (defines output grid)
    ref = np.asarray(fits.getdata(reference_fname), dtype=np.float32)

    aligned_imgs: Dict[str, np.ndarray] = {reference_fname: ref}
    aligned_list: List[np.ndarray] = [ref]

    for fn in fnames:
        if fn == reference_fname:
            continue

        if fn not in transforms:
            if skip_missing_transform:
                continue
            raise KeyError(f"Missing transform for file: {fn}")

        img = np.asarray(fits.getdata(fn), dtype=np.float32)
        tform = transforms[fn]

        registered, _footprint = aa.apply_transform(
            tform,
            img,
            ref,            # target image defines output shape/grid
            fill_value=fill_value,
        )

        reg = np.asarray(registered, dtype=np.float32)
        aligned_imgs[fn] = reg
        aligned_list.append(reg)

    if len(aligned_list) == 0:
        raise RuntimeError("No images available to stack (reference missing?)")

    stack = np.stack(aligned_list, axis=0)  # (N, H, W)

    # Optional sigma clipping
    if sigma_clip is not None and stack.shape[0] > 1:
        mu = np.nanmean(stack, axis=0)
        sd = np.nanstd(stack, axis=0)
        lo = mu - sigma_clip * sd
        hi = mu + sigma_clip * sd
        stack = np.where((stack < lo) | (stack > hi), np.nan, stack)

    # Combine
    if combine == "median":
        stacked = np.nanmedian(stack, axis=0)
    elif combine == "mean":
        stacked = np.nanmean(stack, axis=0)
    else:
        raise ValueError("combine must be 'median' or 'mean'")

    stacked = np.asarray(stacked, dtype=np.float32)
    return (stacked, aligned_imgs) if return_aligned else stacked
