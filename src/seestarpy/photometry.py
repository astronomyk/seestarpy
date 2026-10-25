"""
On-scope photometry and light curves (firmware 9.x, app v3.4.1).

The Seestar can measure stars in every frame it stacks and keep a light
curve for the ones you "record".  The workflow, as the official app runs
it:

1. Put the stacker into photometry mode: :func:`set_photometry_mode`.
2. Goto a target and start stacking as usual
   (:func:`seestarpy.raw.iscope_start_view`, then
   :func:`seestarpy.raw.iscope_start_stack`).
3. The firmware plate-solves and needs APASS reference stars around the
   field.  If the scope has internet (station mode) it downloads them
   itself from ``api.seestar.com``.  If not, the app fetches them and
   pushes them with ``upload_refstar_info``: use
   :func:`query_reference_stars` + :func:`upload_refstar_info`, or the
   one-shot :func:`provide_reference_stars`.  The state of this step is in
   :func:`get_check_state`.
4. Each new frame is measured: :func:`get_photometry_stars` lists every
   star with its instrumental and calibrated magnitudes.
5. Record the stars you care about with :func:`record_star`; the firmware
   then appends one point per frame to their light curve.
6. Read a light curve with :func:`light_curve` (or the raw
   :func:`get_photometry_plot`), save it with :func:`save_light_curve`.
   Finished recordings are listed by :func:`get_photometry_result`.

:func:`get_photometry_wcs` returns the scope's plate solution of the
current photometry frame as FITS WCS keywords.

Method names and JSON keys come from the decompiled app v3.4.1 (Gson
``@SerializedName`` annotations) and the firmware binary.  Calls that need
a photometry frame return ``code 207`` ("fail to operate") or ``267``
("no image") when there is none.
"""

import csv

import requests as _requests

from .connection import send_command, multiple_ips

#: ``stack.capt_type`` value that selects photometry stacking.
PHOTOMETRY_CAPT_TYPE = "photometry"

#: Defaults the app uses for the reference-star query (V mag limit, radius
#: in degrees).
DEFAULT_MAG_LIMIT = 10.0
DEFAULT_RADIUS_DEG = 3.5

_VIZIER_ASU = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
_APASS_TABLE = "II/336/apass9"

# Light-curve point keys, in CSV column order.  ``MJD`` is upper case on
# the wire.
_LC_COLUMNS = ("MJD", "measure_mag", "err", "snr", "ref_mag", "loc_date",
               "id", "is_variable", "radec_deg", "pix")


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

@multiple_ips
def set_photometry_mode(enable=True, wide_cam=None):
    """
    Switch the stacker between photometry and normal stacking.

    The app does this with ``set_setting {"stack": {"capt_type": ...}}``,
    so the mode persists until changed back.

    Parameters
    ----------
    enable : bool
        ``True`` (default) selects ``"photometry"``, ``False`` restores
        ``"stack"``.
    wide_cam : bool, optional
        Set the mode for the wide-angle camera (S30 Pro).  Omitted by
        default.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import photometry
        >>> photometry.set_photometry_mode(True)

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    p = {"stack": {"capt_type": PHOTOMETRY_CAPT_TYPE if enable else "stack"}}
    if wide_cam is not None:
        p["wide_cam"] = bool(wide_cam)
    return send_command({"method": "set_setting", "params": p})


@multiple_ips
def get_photometry_mode():
    """
    Return ``True`` if the stacker is in photometry mode.

    Returns
    -------
    bool or None
        ``None`` if the setting could not be read.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    resp = send_command({"method": "get_setting"})
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), dict):
        return None
    capt = (resp["result"].get("stack") or {}).get("capt_type")
    return capt == PHOTOMETRY_CAPT_TYPE


# ---------------------------------------------------------------------------
# Reference stars
# ---------------------------------------------------------------------------

@multiple_ips
def check_photometry(mag_v=DEFAULT_MAG_LIMIT, offset_deg=DEFAULT_RADIUS_DEG):
    """
    Ask the firmware to prepare photometry for the current field.

    The firmware plate-solves the field and looks for reference stars
    brighter than *mag_v* within *offset_deg*.  Progress and the field
    centre are reported by :func:`get_check_state`.

    Parameters
    ----------
    mag_v : float
        Faint limit of the reference stars (V).  Default 10.0, as in the app.
    offset_deg : float
        Search radius in degrees.  Default 3.5, as in the app.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "check_photometry",
                         "params": {"magV": float(mag_v),
                                    "offsetDeg": float(offset_deg)}})


@multiple_ips
def get_check_state():
    """
    Return the photometry-preparation state from the view state.

    Returns
    -------
    dict or None
        ``iscope_get_app_state()["View"]["CheckPhotoMetry"]``: includes
        ``has_download_ref_star`` (whether reference stars are loaded) and
        ``ra_dec_deg_j2000`` (field centre, degrees), plus nested
        ``PlateSolve`` / ``Exposure`` states.  ``None`` when photometry
        has not been started.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    resp = send_command({"method": "iscope_get_app_state"})
    if not isinstance(resp, dict) or not isinstance(resp.get("result"), dict):
        return None
    view = resp["result"].get("View") or {}
    return view.get("CheckPhotoMetry")


def query_reference_stars(ra_deg, dec_deg, radius_deg=DEFAULT_RADIUS_DEG,
                          mag_limit=DEFAULT_MAG_LIMIT, max_stars=2000,
                          timeout=60):
    """
    Fetch APASS DR9 reference stars from VizieR in ``upload_refstar_info``
    format.

    The firmware itself downloads APASS stars (``api.seestar.com/v2/apass``)
    when it has internet; this gives the same kind of list for a scope that
    is offline.  No Seestar is contacted.

    Parameters
    ----------
    ra_deg, dec_deg : float
        Field centre in **degrees** (J2000).  :func:`get_check_state`
        reports it as ``ra_dec_deg_j2000``.
    radius_deg : float
        Search radius.  Default 3.5.
    mag_limit : float
        Faint V limit.  Default 10.0.
    max_stars : int
        Upper limit on the rows returned.  Default 2000.
    timeout : float
        HTTP timeout in seconds.

    Returns
    -------
    list of dict
        Each with ``sourceId`` (``"APASS J<ra><dec>"``, APASS DR9 has no
        star IDs), ``raDeg``, ``decDeg``, ``magV``, ``emagV`` (``None``
        when APASS gives no error) and
        ``photVariableFlag`` (``"NOT_AVAILABLE"``; APASS has no
        variability flag).

    Raises
    ------
    ConnectionError
        If VizieR is unreachable or answers with an error.
    """
    query = {
        "-source": _APASS_TABLE,
        "-c": f"{ra_deg:.6f} {dec_deg:+.6f}",
        "-c.rd": f"{radius_deg:g}",
        "-out": "RAJ2000,DEJ2000,Vmag,e_Vmag",
        "-out.max": str(int(max_stars)),
        "-sort": "Vmag",
        "Vmag": f"<{mag_limit:g}",
        "-oc.form": "d",
    }
    try:
        resp = _requests.get(_VIZIER_ASU, params=query, timeout=timeout)
        resp.raise_for_status()
    except _requests.RequestException as exc:
        raise ConnectionError(f"VizieR APASS query failed: {exc}") from exc
    return _parse_apass_tsv(resp.text)


def _parse_apass_tsv(text):
    """Turn a VizieR ASU-TSV APASS answer into ``refData`` dicts."""
    stars = []
    header = None
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = [c.strip() for c in line.split("\t")]
        if header is None:
            header = cols
            continue
        if not cols[0] or set(cols[0]) <= {"-", " "}:
            continue      # units line and the dashed separator under it
        row = dict(zip(header, cols))
        try:
            ra = float(row["RAJ2000"])
            dec = float(row["DEJ2000"])
            vmag = float(row["Vmag"])
        except (KeyError, ValueError):
            continue
        try:
            evmag = float(row.get("e_Vmag", "")) or None   # 0 = no error
        except ValueError:
            evmag = None
        stars.append({
            "sourceId": f"APASS J{ra:09.5f}{dec:+09.5f}",
            "raDeg": ra,
            "decDeg": dec,
            "magV": vmag,
            "emagV": evmag,
            "photVariableFlag": "NOT_AVAILABLE",
        })
    return stars


@multiple_ips
def upload_refstar_info(stars):
    """
    Give the Seestar the reference stars for the current photometry field.

    Parameters
    ----------
    stars : list of dict
        Each with ``sourceId``, ``raDeg``, ``decDeg``, ``magV``, ``emagV``
        and ``photVariableFlag``, e.g. from :func:`query_reference_stars`.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "upload_refstar_info",
                         "params": {"refData": list(stars)}})


def provide_reference_stars(ips=None, radius_deg=DEFAULT_RADIUS_DEG,
                            mag_limit=DEFAULT_MAG_LIMIT):
    """
    Query APASS around the current photometry field and upload the stars.

    Reads the field centre from :func:`get_check_state`, so call it after
    the firmware has plate-solved the photometry field.

    Parameters
    ----------
    ips : optional
        Seestar(s) to use, as for any ``@multiple_ips`` function.  With
        several scopes each one gets the stars around its own field.
    radius_deg, mag_limit : float
        Passed to :func:`query_reference_stars`.

    Returns
    -------
    dict or None
        The ``upload_refstar_info`` reply.  ``None`` when the field centre
        is not known yet.  With several IPs, ``{ip: reply}``.
    """
    @multiple_ips
    def _one():
        state = get_check_state()
        centre = (state or {}).get("ra_dec_deg_j2000")
        if not centre or len(centre) < 2:
            return None
        stars = query_reference_stars(centre[0], centre[1],
                                      radius_deg=radius_deg,
                                      mag_limit=mag_limit)
        return upload_refstar_info(stars)

    return _one(ips=ips)


# ---------------------------------------------------------------------------
# Per-frame measurements and WCS
# ---------------------------------------------------------------------------

@multiple_ips
def get_photometry_stars(image_id):
    """
    Return the stars measured in one photometry frame.

    Parameters
    ----------
    image_id : int
        ID of the frame (the image-stream header / ``get_annotate_result``
        ``image_id``).

    Returns
    -------
    dict
        ``result["stars"]``: each with ``id``, ``name``, ``radec_deg``,
        ``pix``, ``measure_mag``, ``err``, ``snr``, ``ref_mag``, ``MJD``,
        ``loc_date``, ``save`` (being recorded), ``is_reference``,
        ``is_variable``, ``is_overexposure`` and ``star_type``.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "get_photometry_stars",
                         "params": {"image_id": int(image_id)}})


@multiple_ips
def get_photometry_wcs():
    """
    Return the plate solution of the current photometry frame.

    Returns
    -------
    dict
        ``result`` with ``IMAGEW``, ``IMAGEH``, ``CRVAL1``, ``CRVAL2``,
        ``CRPIX1``, ``CRPIX2`` and ``CD1_1`` ... ``CD2_2``.  ``code 267``
        ("no image") without a photometry frame.  See :func:`wcs_header`.

    Notes
    -----
    New in firmware 9.x.  Accepts the ``ips`` keyword for multi-Seestar
    operation.
    """
    return send_command({"method": "get_photometry_wcs"})


def wcs_header(wcs_result):
    """
    Convert a :func:`get_photometry_wcs` reply to FITS WCS keywords.

    Parameters
    ----------
    wcs_result : dict
        The full reply or just its ``result``.

    Returns
    -------
    dict
        ``NAXIS1``/``NAXIS2``, ``CTYPE1``/``CTYPE2`` (``RA---TAN`` /
        ``DEC--TAN``), ``CUNIT``, ``CRVAL``, ``CRPIX`` and ``CD`` keywords,
        ready for ``astropy.wcs.WCS(header)`` or a FITS header.

    Raises
    ------
    ValueError
        If the reply carries no solution.
    """
    res = wcs_result.get("result", wcs_result) if isinstance(wcs_result, dict) else None
    if not isinstance(res, dict) or "CRVAL1" not in res:
        raise ValueError(f"No WCS in reply: {wcs_result!r}")
    hdr = {
        "NAXIS": 2,
        "NAXIS1": res.get("IMAGEW"),
        "NAXIS2": res.get("IMAGEH"),
        "CTYPE1": "RA---TAN",
        "CTYPE2": "DEC--TAN",
        "CUNIT1": "deg",
        "CUNIT2": "deg",
    }
    for key in ("CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
                "CD1_1", "CD1_2", "CD2_1", "CD2_2"):
        if res.get(key) is not None:
            hdr[key] = res[key]
    return hdr


# ---------------------------------------------------------------------------
# Recording and light curves
# ---------------------------------------------------------------------------

@multiple_ips
def set_photometry(star_id, save=True, name=None):
    """
    Start or stop recording the light curve of one star.

    Parameters
    ----------
    star_id : str
        ``id`` of the star in :func:`get_photometry_stars`.
    save : bool
        ``True`` (default) to record, ``False`` to stop.
    name : str, optional
        Display name for the recording.

    Returns
    -------
    dict

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    p = {"id": str(star_id), "save": bool(save)}
    if name is not None:
        p["name"] = name
    return send_command({"method": "set_photometry", "params": p})


def record_star(star_id, name=None, ips=None):
    """Start recording a star's light curve.  See :func:`set_photometry`."""
    return set_photometry(star_id, save=True, name=name, ips=ips)


def stop_recording(star_id, ips=None):
    """Stop recording a star's light curve.  See :func:`set_photometry`."""
    return set_photometry(star_id, save=False, ips=ips)


@multiple_ips
def get_saved_photometry_stars():
    """
    List the stars whose light curves are being recorded.

    Returns
    -------
    dict
        ``result["PhometryStars"]`` (sic): each with ``id``, ``star_name``,
        ``radec_deg``, ``save``, ``startTime`` and ``is_variable``.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "get_saved_photometry_stars"})


def recorded_stars(ips=None):
    """
    Return the list of recorded stars from :func:`get_saved_photometry_stars`.

    Returns
    -------
    list of dict
        Empty when nothing is recorded or the call failed.  With several
        IPs, ``{ip: list}``.
    """
    @multiple_ips
    def _one():
        resp = get_saved_photometry_stars()
        res = resp.get("result") if isinstance(resp, dict) else None
        return list((res or {}).get("PhometryStars") or [])

    return _one(ips=ips)


@multiple_ips
def get_photometry_plot(star_id):
    """
    Return the light curve recorded for one star.

    Parameters
    ----------
    star_id : str
        ``id`` of the star.

    Returns
    -------
    dict
        ``result`` with ``name``, ``save`` and ``stars``: one point per
        measured frame with ``MJD``, ``measure_mag``, ``err``, ``snr``,
        ``ref_mag``, ``loc_date``, ``radec_deg``, ``pix`` and
        ``is_variable``.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "get_photometry_plot",
                         "params": {"id": str(star_id)}})


def light_curve(star_id, ips=None):
    """
    Return a star's light curve as a list of points sorted by MJD.

    Parameters
    ----------
    star_id : str
        ``id`` of the star.

    Returns
    -------
    list of dict
        The ``stars`` points of :func:`get_photometry_plot`, sorted by
        ``MJD``.  Empty when there is no light curve.  With several IPs,
        ``{ip: list}``.
    """
    @multiple_ips
    def _one():
        return _points(get_photometry_plot(star_id))

    return _one(ips=ips)


def _points(resp):
    res = resp.get("result") if isinstance(resp, dict) else None
    pts = [p for p in ((res or {}).get("stars") or []) if isinstance(p, dict)]
    return sorted(pts, key=lambda p: (p.get("MJD") is None, p.get("MJD")))


def save_light_curve(points, path):
    """
    Write light-curve points to a CSV file.

    Parameters
    ----------
    points : list of dict
        Output of :func:`light_curve`.
    path : str or path-like
        Destination file.

    Returns
    -------
    int
        Number of rows written.
    """
    extra = sorted({k for p in points for k in p} - set(_LC_COLUMNS))
    columns = list(_LC_COLUMNS) + extra
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for p in points:
            writer.writerow({k: (" ".join(map(str, v)) if isinstance(v, list) else v)
                             for k, v in p.items()})
    return len(points)


@multiple_ips
def get_photometry_result():
    """
    List the light-curve files the Seestar has saved.

    Returns
    -------
    dict
        ``result`` with ``path`` and ``files``: each with ``name``,
        ``star_name``, ``path``, ``last_save_time``, ``is_variable`` and
        ``ra_dec_deg_j2000``.  ``code 207`` when there are none.  The
        firmware stores them as CSV, so they can also be downloaded with
        :mod:`seestarpy.data`.

    Notes
    -----
    Accepts the ``ips`` keyword for multi-Seestar operation.
    """
    return send_command({"method": "get_photometry_result"})
