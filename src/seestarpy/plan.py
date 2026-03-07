import math
import random
import warnings
import xml.etree.ElementTree as _ET
from datetime import datetime
from urllib.parse import quote as _url_quote

import requests as _requests

from .connection import send_command
from .raw import iscope_get_app_state

_N_EDGE_POINTS = 50


def get_running_plan():
    """
    Return the currently running observation plan, or ``None`` if no plan
    is active.

    This queries ``iscope_get_app_state`` and extracts the ``ViewPlan``
    key, which is how the official Seestar app checks plan status.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Returns
    -------
    dict or None
        The ``ViewPlan`` state dict when a plan is loaded (even if
        stopped/cancelled), or ``None`` if no plan data is present.
        The dict includes ``state`` (``"working"``, ``"cancel"``, etc.)
        and ``plan`` with the full plan payload including per-target
        ``state``, ``lapse_ms``, and ``skip`` fields added by the
        firmware.

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> vp = plan.get_running_plan()
        >>> if vp and vp["state"] == "working":
        ...     print(f"Running: {vp['plan']['plan_name']}")

    """
    resp = iscope_get_app_state()
    result = resp.get("result")
    if isinstance(result, dict):
        return result.get("ViewPlan")
    return None


def set_view_plan(plan):
    """
    Send an observation plan to the Seestar and start executing it.

    Parameters
    ----------
    plan : dict
        A plan dictionary with keys ``plan_name`` (str),
        ``update_time_seestar`` (str, format ``"yyyy.MM.dd"``), and
        ``list`` (list of target dicts).  Each target dict has:

        - ``target_id`` (int): 9-digit unique identifier.
        - ``target_name`` (str): Display name (e.g. ``"M 31"``).
        - ``alias_name`` (str): Alias or empty string ``""``.
        - ``target_ra_dec`` (list[float, float]): ``[RA_hours, Dec_degrees]``.
        - ``lp_filter`` (bool): Enable the light-pollution filter for this
          target.
        - ``start_min`` (int): Start time as minutes since local midnight.
        - ``duration_min`` (int): Observation duration in minutes.

    Returns
    -------
    dict

    Notes
    -----
    .. note:: Payload format confirmed via traffic capture from the
       official Seestar app v3.0.2 on 2026-02-24.

    **RA convention**: ``target_ra_dec`` uses the same convention as
    :func:`~seestarpy.raw.iscope_start_view` — RA in **decimal
    hour-angle** [0, 24) and Dec in **decimal degrees** [-90, 90].
    The decompiled ``SetViewPlanCmd.java`` does not divide RA by 15
    because the app already stores RA in hour-angle.

    **start_min**: This is **not** a relative offset from when the plan
    starts.  It is the absolute **minutes since local midnight**, using the
    Seestar's internal clock (which is synced to the phone/host local
    time via :func:`~seestarpy.raw.pi_set_time`).
    For example, 22:30 = ``1350``, 23:00 = ``1380``.
    For targets after midnight, use values above 1440
    (e.g. 01:30 AM = ``1530``).

    **duration_min**: Observation duration in minutes.  The official app
    displays plans on a chart with 10-minute resolution, but the firmware
    receives the raw integer -- sub-10-minute durations are valid at the
    protocol level.

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> # M42 at 22:30 for 30 min, then M31 at 23:00 for 45 min
        >>> my_plan = {
        ...     "plan_name": "Evening Session",
        ...     "update_time_seestar": "2026.02.23",
        ...     "list": [
        ...         {
        ...             "target_id": 123456789,
        ...             "target_name": "M42",
        ...             "alias_name": "Orion Nebula",
        ...             "target_ra_dec": [5.588, -5.39],
        ...             "lp_filter": True,
        ...             "start_min": 1350,
        ...             "duration_min": 30,
        ...         },
        ...         {
        ...             "target_id": 123456790,
        ...             "target_name": "M31",
        ...             "alias_name": "Andromeda Galaxy",
        ...             "target_ra_dec": [0.712, 41.27],
        ...             "lp_filter": False,
        ...             "start_min": 1380,
        ...             "duration_min": 45,
        ...         },
        ...     ],
        ... }
        >>> plan.set_view_plan(my_plan)

    """
    params = {'method': 'set_view_plan', 'params': plan}
    return send_command(params)


def stop_view_plan():
    """
    Stop the currently executing observation plan.

    This is the method the official Seestar app uses to stop a running plan.
    It sends ``stop_func`` with ``{"name": "ViewPlan"}``.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.stop_view_plan()

    """
    params = {'method': 'stop_func', 'params': {'name': 'ViewPlan'}}
    return send_command(params)


def _generate_target_ids(n):
    """Return *n* unique random 9-digit integers for use as target IDs."""
    ids = set()
    while len(ids) < n:
        ids.add(random.randint(100_000_000, 999_999_999))
    return list(ids)


def create_mosaic_plan(
    plan_name,
    center_ra,
    center_dec,
    width,
    height,
    delta_ra,
    delta_dec,
    t_total,
    start_min,
    lp_filter=False,
    target_name_prefix="Mosaic",
):
    """
    Create an observation plan that tiles a rectangular sky region.

    The Seestar S50 FOV is roughly 0.75 x 1.33 degrees — too small for many
    extended objects.  This function generates a plan dictionary with
    individual pointings arranged in a grid, ready to be sent with
    :func:`set_view_plan`.  No network I/O is performed.

    Panels are traversed in **boustrophedon** (snake) order: even Dec rows
    go left-to-right in RA, odd rows go right-to-left.  This minimises
    slew distance between consecutive panels.

    Parameters
    ----------
    plan_name : str
        Human-readable name for the plan.
    center_ra : float
        Right ascension of the mosaic centre in decimal hours [0, 24).
    center_dec : float
        Declination of the mosaic centre in decimal degrees [-90, 90].
    width : float
        Angular extent in RA on the sky, in degrees.  Use 0 for a single
        column of panels.
    height : float
        Angular extent in Dec, in degrees.  Use 0 for a single row.
    delta_ra : float
        Panel spacing in the RA direction, in degrees (> 0).
    delta_dec : float
        Panel spacing in the Dec direction, in degrees (> 0).
    t_total : float
        Total observation time in minutes, divided equally among panels.
    start_min : int
        Start time as minutes since local midnight (same convention as
        :func:`set_view_plan`).
    lp_filter : bool, optional
        Enable the light-pollution filter for every panel (default False).
    target_name_prefix : str, optional
        Prefix for panel names (default ``"Mosaic"``).  Panels are named
        ``"{prefix}_01"``, ``"{prefix}_02"``, etc.

    Returns
    -------
    dict
        A plan dictionary suitable for :func:`set_view_plan`.

    Raises
    ------
    ValueError
        If any parameter is out of range.

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> mosaic = plan.create_mosaic_plan(
        ...     plan_name="NGC 7000 Mosaic",
        ...     center_ra=20.99,       # ~20h 59m
        ...     center_dec=44.53,
        ...     width=3.0,
        ...     height=2.0,
        ...     delta_ra=1.0,
        ...     delta_dec=1.0,
        ...     t_total=180,
        ...     start_min=1320,        # 22:00
        ... )
        >>> len(mosaic["list"])
        6
        >>> plan.set_view_plan(mosaic)

    """
    # --- validate inputs ---
    if not 0 <= center_ra < 24:
        raise ValueError(f"center_ra must be in [0, 24), got {center_ra}")
    if not -90 <= center_dec <= 90:
        raise ValueError(f"center_dec must be in [-90, 90], got {center_dec}")
    if width < 0:
        raise ValueError(f"width must be >= 0, got {width}")
    if height < 0:
        raise ValueError(f"height must be >= 0, got {height}")
    if delta_ra <= 0:
        raise ValueError(f"delta_ra must be > 0, got {delta_ra}")
    if delta_dec <= 0:
        raise ValueError(f"delta_dec must be > 0, got {delta_dec}")
    if abs(center_dec) == 90:
        raise ValueError(
            "Mosaics at exactly ±90° declination are not supported "
            "(cos(dec) = 0 causes division by zero in RA spacing)."
        )
    if abs(center_dec) > 85:
        warnings.warn(
            f"Declination {center_dec}° is near a pole; "
            "RA spacing will be very large and the mosaic may not tile correctly.",
            stacklevel=2,
        )

    # --- grid dimensions ---
    n_ra = max(1, math.ceil(width / delta_ra)) if width > 0 else 1
    n_dec = max(1, math.ceil(height / delta_dec)) if height > 0 else 1
    n_panels = n_ra * n_dec

    # --- cos(dec) correction for RA spacing ---
    cos_dec = math.cos(math.radians(center_dec))
    ra_step_hours = delta_ra / (15.0 * cos_dec)

    dec_step_deg = delta_dec

    # --- symmetric grid offsets ---
    ra_offsets = [
        (i - (n_ra - 1) / 2.0) * ra_step_hours for i in range(n_ra)
    ]
    dec_offsets = [
        (j - (n_dec - 1) / 2.0) * dec_step_deg for j in range(n_dec)
    ]

    # --- time allocation ---
    duration_per_panel = max(1, int(t_total // n_panels))

    # --- generate targets with boustrophedon traversal ---
    target_ids = _generate_target_ids(n_panels)
    targets = []
    panel_num = 0

    for j, dec_off in enumerate(dec_offsets):
        ra_order = ra_offsets if j % 2 == 0 else list(reversed(ra_offsets))
        for ra_off in ra_order:
            ra = (center_ra + ra_off) % 24.0
            dec = center_dec + dec_off
            targets.append({
                "target_id": target_ids[panel_num],
                "target_name": f"{target_name_prefix}_{panel_num + 1:02d}",
                "alias_name": "",
                "target_ra_dec": [ra, dec],
                "lp_filter": lp_filter,
                "start_min": start_min + panel_num * duration_per_panel,
                "duration_min": duration_per_panel,
            })
            panel_num += 1

    return {
        "plan_name": plan_name,
        "update_time_seestar": datetime.now().strftime("%Y.%m.%d"),
        "list": targets,
    }


def _spherical_centroid(corners):
    """Centroid of RA/Dec points via Cartesian averaging.

    Parameters
    ----------
    corners : list of (float, float)
        Each element is ``(ra_hours, dec_deg)``.

    Returns
    -------
    (float, float)
        Centroid as ``(ra_rad, dec_rad)``.
    """
    x = y = z = 0.0
    for ra_h, dec_d in corners:
        ra = math.radians(ra_h * 15.0)
        dec = math.radians(dec_d)
        cd = math.cos(dec)
        x += cd * math.cos(ra)
        y += cd * math.sin(ra)
        z += math.sin(dec)
    x /= len(corners)
    y /= len(corners)
    z /= len(corners)
    r = math.sqrt(x * x + y * y + z * z)
    if r < 1e-12:
        raise ValueError("Degenerate corners: centroid is at the origin.")
    dec0 = math.asin(z / r)
    ra0 = math.atan2(y, x) % (2 * math.pi)
    return ra0, dec0


def _gnomonic_forward(ra_rad, dec_rad, ra0, dec0):
    """Forward gnomonic (tangent-plane) projection.

    Parameters
    ----------
    ra_rad, dec_rad : float
        Point coordinates in radians.
    ra0, dec0 : float
        Tangent point (projection centre) in radians.

    Returns
    -------
    (float, float)
        Tangent-plane coordinates ``(xi, eta)`` in radians.
    """
    cos_dec = math.cos(dec_rad)
    sin_dec = math.sin(dec_rad)
    cos_dec0 = math.cos(dec0)
    sin_dec0 = math.sin(dec0)
    dra = ra_rad - ra0
    cos_c = sin_dec0 * sin_dec + cos_dec0 * cos_dec * math.cos(dra)
    if cos_c <= 0:
        raise ValueError("Point is more than 90° from tangent centre.")
    xi = cos_dec * math.sin(dra) / cos_c
    eta = (cos_dec0 * sin_dec - sin_dec0 * cos_dec * math.cos(dra)) / cos_c
    return xi, eta


def _gnomonic_inverse(xi, eta, ra0, dec0):
    """Inverse gnomonic projection: tangent-plane back to sphere.

    Parameters
    ----------
    xi, eta : float
        Tangent-plane coordinates in radians.
    ra0, dec0 : float
        Tangent point in radians.

    Returns
    -------
    (float, float)
        Spherical coordinates ``(ra_rad, dec_rad)``.
    """
    rho = math.sqrt(xi * xi + eta * eta)
    if rho < 1e-15:
        return ra0, dec0
    c = math.atan(rho)
    sin_c = math.sin(c)
    cos_c = math.cos(c)
    cos_dec0 = math.cos(dec0)
    sin_dec0 = math.sin(dec0)
    dec = math.asin(cos_c * sin_dec0 + eta * sin_c * cos_dec0 / rho)
    ra = ra0 + math.atan2(
        xi * sin_c,
        rho * cos_dec0 * cos_c - eta * sin_dec0 * sin_c,
    )
    ra = ra % (2 * math.pi)
    return ra, dec


def _point_in_polygon(px, py, poly):
    """Ray-casting point-in-polygon test.

    Parameters
    ----------
    px, py : float
        Test point.
    poly : list of (float, float)
        Polygon vertices (closed automatically).

    Returns
    -------
    bool
    """
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def create_polygon_plan(
    plan_name,
    corners,
    delta_ra,
    delta_dec,
    t_total,
    start_min,
    lp_filter=False,
    target_name_prefix="Poly",
):
    """
    Create an observation plan filling an arbitrary polygon on the sky.

    Unlike :func:`create_mosaic_plan` which tiles an axis-aligned rectangle,
    this function accepts 3 or more RA/Dec corner pairs defining a simple
    (non-self-intersecting) polygon that may be non-rectangular or tilted
    relative to the equatorial grid.  A gnomonic tangent-plane projection is
    used internally, so cos(dec) correction and RA wraparound near 0 h/24 h
    are handled automatically.

    Panels are traversed in **boustrophedon** (snake) order within the
    tangent-plane grid.  No network I/O is performed.

    Parameters
    ----------
    plan_name : str
        Human-readable name for the plan.
    corners : list of (float, float)
        Three or more ``(ra_hours, dec_deg)`` tuples defining the polygon
        boundary, ordered either clockwise or counter-clockwise.  Edges
        must not cross each other (simple polygon).
    delta_ra : float
        Grid spacing in the RA (xi) direction of the tangent plane, in
        degrees (> 0).
    delta_dec : float
        Grid spacing in the Dec (eta) direction of the tangent plane, in
        degrees (> 0).
    t_total : float
        Total observation time in minutes, divided equally among panels.
    start_min : int
        Start time as minutes since local midnight (same convention as
        :func:`set_view_plan`).
    lp_filter : bool, optional
        Enable the light-pollution filter for every panel (default False).
    target_name_prefix : str, optional
        Prefix for panel names (default ``"Poly"``).

    Returns
    -------
    dict
        A plan dictionary suitable for :func:`set_view_plan`.

    Raises
    ------
    ValueError
        If ``corners`` has fewer than 3 elements, spacings are not
        positive, or the polygon is degenerate (zero area).

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> # Quadrilateral
        >>> quad = plan.create_polygon_plan(
        ...     plan_name="Veil Nebula Quad",
        ...     corners=[
        ...         (20.75, 30.0),
        ...         (20.95, 30.0),
        ...         (20.95, 32.0),
        ...         (20.75, 32.0),
        ...     ],
        ...     delta_ra=0.5,
        ...     delta_dec=0.5,
        ...     t_total=120,
        ...     start_min=1320,
        ... )
        >>> # Pentagon
        >>> penta = plan.create_polygon_plan(
        ...     plan_name="Five-sided region",
        ...     corners=[
        ...         (12.0, 0.0), (12.1, -0.5), (12.2, 0.0),
        ...         (12.15, 0.5), (12.05, 0.5),
        ...     ],
        ...     delta_ra=0.3,
        ...     delta_dec=0.3,
        ...     t_total=90,
        ...     start_min=1320,
        ... )
        >>> plan.set_view_plan(quad)

    """
    # --- validate inputs ---
    if len(corners) < 3:
        raise ValueError(f"corners must have at least 3 elements, got {len(corners)}")
    for i, (ra, dec) in enumerate(corners):
        if not 0 <= ra < 24:
            raise ValueError(f"Corner {i}: RA must be in [0, 24), got {ra}")
        if not -90 <= dec <= 90:
            raise ValueError(f"Corner {i}: Dec must be in [-90, 90], got {dec}")
    if delta_ra <= 0:
        raise ValueError(f"delta_ra must be > 0, got {delta_ra}")
    if delta_dec <= 0:
        raise ValueError(f"delta_dec must be > 0, got {delta_dec}")

    for _, dec in corners:
        if abs(dec) > 85:
            warnings.warn(
                f"Corner declination {dec}° is near a pole; "
                "tangent-plane projection may introduce distortion.",
                stacklevel=2,
            )
            break

    # --- Step 1: Centroid ---
    ra0, dec0 = _spherical_centroid(corners)

    # --- Step 2: Forward gnomonic projection of corners ---
    proj_corners = []
    for ra_h, dec_d in corners:
        ra_rad = math.radians(ra_h * 15.0)
        dec_rad = math.radians(dec_d)
        xi, eta = _gnomonic_forward(ra_rad, dec_rad, ra0, dec0)
        proj_corners.append((xi, eta))

    # Check for degenerate polygon (shoelace area)
    n_corners = len(proj_corners)
    area = 0.0
    for i in range(n_corners):
        x1, y1 = proj_corners[i]
        x2, y2 = proj_corners[(i + 1) % n_corners]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0
    if area < 1e-15:
        raise ValueError("Degenerate polygon: zero area in tangent plane.")

    # --- Step 3: Grid generation ---
    delta_ra_rad = math.radians(delta_ra)
    delta_dec_rad = math.radians(delta_dec)

    xi_vals = [p[0] for p in proj_corners]
    eta_vals = [p[1] for p in proj_corners]
    xi_min, xi_max = min(xi_vals), max(xi_vals)
    eta_min, eta_max = min(eta_vals), max(eta_vals)

    # Centre the grid within the bounding box
    n_xi = max(1, math.ceil((xi_max - xi_min) / delta_ra_rad))
    n_eta = max(1, math.ceil((eta_max - eta_min) / delta_dec_rad))
    xi_center = (xi_min + xi_max) / 2.0
    eta_center = (eta_min + eta_max) / 2.0

    grid_points = []
    for j in range(n_eta):
        eta = eta_center + (j - (n_eta - 1) / 2.0) * delta_dec_rad
        for i in range(n_xi):
            xi = xi_center + (i - (n_xi - 1) / 2.0) * delta_ra_rad
            grid_points.append((xi, eta, j, i))

    # --- Step 4: Point-in-polygon filter ---
    inside_points = [
        (xi, eta, j, i)
        for xi, eta, j, i in grid_points
        if _point_in_polygon(xi, eta, proj_corners)
    ]

    # If no points inside, place a single pointing at the centroid
    if not inside_points:
        inside_points = [(0.0, 0.0, 0, 0)]

    # --- Step 5: Inverse gnomonic projection ---
    sky_points = []
    for xi, eta, row, col in inside_points:
        ra_rad, dec_rad = _gnomonic_inverse(xi, eta, ra0, dec0)
        ra_hours = math.degrees(ra_rad) / 15.0
        dec_deg = math.degrees(dec_rad)
        ra_hours = ra_hours % 24.0
        sky_points.append((ra_hours, dec_deg, row, col))

    # --- Step 6: Boustrophedon ordering ---
    # Group by row, then alternate column sort direction
    sky_points.sort(key=lambda p: (p[2], p[3]))
    rows = {}
    for ra_h, dec_d, row, col in sky_points:
        rows.setdefault(row, []).append((ra_h, dec_d, col))
    ordered = []
    for idx, row_key in enumerate(sorted(rows.keys())):
        row_pts = rows[row_key]
        row_pts.sort(key=lambda p: p[2], reverse=(idx % 2 == 1))
        for ra_h, dec_d, _ in row_pts:
            ordered.append((ra_h, dec_d))

    # --- Step 7: Build plan dict ---
    n_panels = len(ordered)
    duration_per_panel = max(1, int(t_total // n_panels))
    target_ids = _generate_target_ids(n_panels)
    targets = []

    for panel_num, (ra_h, dec_d) in enumerate(ordered):
        targets.append({
            "target_id": target_ids[panel_num],
            "target_name": f"{target_name_prefix}_{panel_num + 1:02d}",
            "alias_name": "",
            "target_ra_dec": [ra_h, dec_d],
            "lp_filter": lp_filter,
            "start_min": start_min + panel_num * duration_per_panel,
            "duration_min": duration_per_panel,
        })

    return {
        "plan_name": plan_name,
        "update_time_seestar": datetime.now().strftime("%Y.%m.%d"),
        "list": targets,
    }


#: Alias — the original name before generalisation to arbitrary polygons.
create_quadrilateral_plan = create_polygon_plan


_SESAME_URL = "https://cdsweb.u-strasbg.fr/cgi-bin/nph-sesame/-ox/SNV"


def resolve_name(name):
    """
    Resolve an astronomical object name to RA/Dec using the CDS Sesame
    name resolver.

    Sesame queries SIMBAD, NED, and VizieR in sequence, so most common
    designations work (Messier, NGC, IC, HD, HIP, Bayer, etc.).

    Parameters
    ----------
    name : str
        Object designation, e.g. ``"M42"``, ``"NGC 884"``, ``"HD 126675"``.

    Returns
    -------
    (float, float)
        ``(ra_hours, dec_deg)`` in the same convention used by
        :func:`set_view_plan` — RA as decimal hours [0, 24), Dec as
        decimal degrees [-90, 90].

    Raises
    ------
    LookupError
        If the name cannot be resolved (not found in any catalogue).
    ConnectionError
        If the Sesame service is unreachable.

    Examples
    --------
    ::

        >>> from seestarpy.plan import resolve_name
        >>> ra, dec = resolve_name("M42")
        >>> print(f"RA={ra:.4f}h  Dec={dec:.2f}°")
        RA=5.5881h  Dec=-5.39°

    """
    url = f"{_SESAME_URL}?{_url_quote(name)}"
    try:
        resp = _requests.get(url, timeout=10)
        resp.raise_for_status()
    except _requests.RequestException as exc:
        raise ConnectionError(
            f"Could not reach CDS Sesame service: {exc}"
        ) from exc

    root = _ET.fromstring(resp.text)
    ra_el = root.find(".//jradeg")
    dec_el = root.find(".//jdedeg")

    if ra_el is None or dec_el is None:
        raise LookupError(
            f"Could not resolve '{name}' — not found in SIMBAD/NED/VizieR."
        )

    ra_deg = float(ra_el.text)
    dec_deg = float(dec_el.text)
    ra_hours = ra_deg / 15.0
    return ra_hours, dec_deg


def _parse_hhmm(time_str):
    """Parse ``"hh:mm"`` to minutes since midnight."""
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Time must be 'hh:mm', got '{time_str}'")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time '{time_str}'")
    return h * 60 + m


def create_named_plan(
    plan_name,
    targets,
    end_time,
    lp_filter=False,
):
    """
    Create an observation plan from a list of targets.

    Targets can be specified by name (resolved automatically via the CDS
    Sesame service — SIMBAD/NED/VizieR) or by explicit RA/Dec
    coordinates.  Each target observes from its start time until the next
    target begins; the last target observes until *end_time*.

    Parameters
    ----------
    plan_name : str
        Human-readable name for the plan.
    targets : list of tuple
        Each element is ``(target, start_time)`` or
        ``(target, start_time, lp_filter)``, where:

        - *target* — either a **string** (object designation such as
          ``"M42"``, ``"NGC 884"``, ``"HD 126675"``, resolved via
          Sesame) or a **(ra_hours, dec_deg) tuple/list** giving
          explicit coordinates.
        - *start_time* (str) — local start time as ``"hh:mm"``
          (24-hour format).
        - *lp_filter* (bool, optional) — per-target light-pollution
          filter override.  If omitted, the function-level *lp_filter*
          default is used.

        Times that are earlier than the previous target's start time are
        assumed to be after midnight (next calendar day).
    end_time : str
        When the last target should stop observing, as ``"hh:mm"``.
        If earlier than the last target's start, it is treated as
        post-midnight.
    lp_filter : bool, optional
        Default light-pollution filter setting for targets that don't
        specify one (default ``False``).

    Returns
    -------
    dict
        A plan dictionary suitable for :func:`set_view_plan`.

    Raises
    ------
    ValueError
        If *targets* is empty or times are malformed.
    LookupError
        If a target name string cannot be resolved.
    ConnectionError
        If the CDS Sesame service is unreachable.

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> p = plan.create_named_plan(
        ...     plan_name="Evening Session",
        ...     targets=[
        ...         ("M42", "21:00"),                  # resolved via Sesame
        ...         ("NGC 884", "22:30", True),        # with LP filter
        ...         ((0.712, 41.27), "23:45"),          # explicit RA/Dec
        ...     ],
        ...     end_time="01:00",
        ... )
        >>> plan.set_view_plan(p)

    """
    if not targets:
        raise ValueError("targets must not be empty")

    # --- Parse target list ---
    parsed = []
    for entry in targets:
        if len(entry) == 2:
            target_spec, start_str = entry
            use_lp = lp_filter
        elif len(entry) == 3:
            target_spec, start_str, use_lp = entry
        else:
            raise ValueError(
                f"Each target must be (target, time) or "
                f"(target, time, lp_filter), got {len(entry)} elements"
            )

        # Determine if target_spec is a name (str) or coords (sequence)
        if isinstance(target_spec, str):
            label = target_spec
            coords_val = None  # resolve later
        else:
            try:
                ra_h, dec_d = target_spec
            except (TypeError, ValueError):
                raise ValueError(
                    f"Target must be a name string or (ra_hours, dec_deg) "
                    f"pair, got {target_spec!r}"
                )
            label = f"RA{ra_h:.3f}_Dec{dec_d:+.2f}"
            coords_val = (float(ra_h), float(dec_d))

        start = _parse_hhmm(start_str)
        parsed.append((label, start, use_lp, coords_val))

    end_min = _parse_hhmm(end_time)

    # --- Handle midnight wraparound ---
    # Convert to monotonically increasing minutes-since-midnight.
    # If a time is earlier than the previous, add 1440 (next day).
    for i in range(1, len(parsed)):
        while parsed[i][1] <= parsed[i - 1][1]:
            parsed[i] = (parsed[i][0], parsed[i][1] + 1440,
                         parsed[i][2], parsed[i][3])
    while end_min <= parsed[-1][1]:
        end_min += 1440

    # --- Resolve coordinates (only for named targets) ---
    resolved = {}
    for label, _, _, coords_val in parsed:
        if coords_val is None and label not in resolved:
            resolved[label] = resolve_name(label)

    # --- Build plan ---
    target_ids = _generate_target_ids(len(parsed))
    plan_targets = []

    for i, (label, start, use_lp, coords_val) in enumerate(parsed):
        next_start = parsed[i + 1][1] if i + 1 < len(parsed) else end_min
        duration = next_start - start
        if duration <= 0:
            raise ValueError(
                f"Target '{label}' has non-positive duration ({duration} min)"
            )
        ra_h, dec_d = coords_val if coords_val is not None else resolved[label]
        plan_targets.append({
            "target_id": target_ids[i],
            "target_name": label,
            "alias_name": "",
            "target_ra_dec": [ra_h, dec_d],
            "lp_filter": use_lp,
            "start_min": start,
            "duration_min": duration,
        })

    return {
        "plan_name": plan_name,
        "update_time_seestar": datetime.now().strftime("%Y.%m.%d"),
        "list": plan_targets,
    }


def _mollweide_xy(lon_rad, lat_rad):
    """Project longitude and latitude (radians) to Mollweide *x*, *y*."""
    import numpy as np

    lon = np.asarray(lon_rad, dtype=float)
    lat = np.asarray(lat_rad, dtype=float)

    # Solve 2θ + sin(2θ) = π·sin(φ) via Newton's method
    theta = lat.copy()
    target = np.pi * np.sin(lat)
    for _ in range(30):
        denom = 2.0 + 2.0 * np.cos(2.0 * theta)
        denom = np.where(np.abs(denom) < 1e-15, 1e-15, denom)
        dt = -(2.0 * theta + np.sin(2.0 * theta) - target) / denom
        theta += dt
        if np.all(np.abs(dt) < 1e-12):
            break

    x = (2.0 * np.sqrt(2.0) / np.pi) * lon * np.cos(theta)
    y = np.sqrt(2.0) * np.sin(theta)
    return x, y


def _nice_grid_step(extent_deg):
    """Return a grid step in degrees that gives ~4-6 lines across *extent_deg*."""
    for step in (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 45, 90):
        if step >= extent_deg / 6:
            return step
    return 90


def plot_mosaic_plan(plan, fov_width=0.75, fov_height=1.33, ax=None):
    """
    Plot panel borders of a mosaic plan on a Mollweide projection.

    The view is zoomed to 150 % of the area covered by the panel
    footprints, with Mollweide grid lines (RA meridians and Dec
    parallels) drawn for reference.  Each panel is drawn as a closed
    rectangle in RA/Dec space, assuming an equatorial mount (panels
    axis-aligned).

    Because matplotlib's built-in Mollweide axes do not support
    zooming, coordinates are projected manually and drawn on a
    standard rectilinear axes.

    Parameters
    ----------
    plan : dict
        A plan dictionary (from :func:`create_mosaic_plan` or hand-built)
        containing ``"plan_name"`` and ``"list"`` with target dicts that
        each have ``"target_ra_dec"`` and ``"target_name"``.
    fov_width : float, optional
        Field-of-view width in degrees (RA direction on the sky).
        Default is 0.75 (Seestar S50).
    fov_height : float, optional
        Field-of-view height in degrees (Dec direction).
        Default is 1.33 (Seestar S50).
    ax : matplotlib.axes.Axes or None, optional
        A rectilinear axes to plot on.  If ``None``, a new figure and
        axes are created.

    Returns
    -------
    matplotlib.axes.Axes
        The axes with panel outlines, labels, and grid lines plotted.

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> mosaic = plan.create_mosaic_plan(
        ...     "NGC 7000", 20.99, 44.53, 3.0, 2.0, 1.0, 1.0, 180, 1320,
        ... )
        >>> ax = plan.plot_mosaic_plan(mosaic)

    """
    import matplotlib.pyplot as plt
    import numpy as np

    # --- Collect panel extents in RA/Dec ---
    ra_edges = []
    dec_edges = []
    panels_info = []

    for target in plan["list"]:
        ra_h, dec_d = target["target_ra_dec"]
        cos_dec = math.cos(math.radians(dec_d))
        half_dec = fov_height / 2.0
        half_ra = fov_width / (2.0 * 15.0 * cos_dec)
        ra_edges.extend([ra_h - half_ra, ra_h + half_ra])
        dec_edges.extend([dec_d - half_dec, dec_d + half_dec])
        panels_info.append((ra_h, dec_d, half_ra, half_dec, target["target_name"]))

    ra_lo, ra_hi = min(ra_edges), max(ra_edges)
    dec_lo, dec_hi = min(dec_edges), max(dec_edges)

    # Expand to 150% of area (sqrt(1.5) per linear dimension)
    scale = math.sqrt(1.5)
    ra_margin = max((ra_hi - ra_lo) * (scale - 1) / 2, 0.02)
    dec_margin = max((dec_hi - dec_lo) * (scale - 1) / 2, 0.1)

    view_ra = (ra_lo - ra_margin, ra_hi + ra_margin)
    view_dec = (dec_lo - dec_margin, dec_hi + dec_margin)

    # --- Create axes ---
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_aspect("equal")

    # --- Grid lines ---
    ra_extent_deg = (view_ra[1] - view_ra[0]) * 15
    dec_extent_deg = view_dec[1] - view_dec[0]
    ra_step_h = _nice_grid_step(ra_extent_deg) / 15.0
    dec_step = _nice_grid_step(dec_extent_deg)

    # RA meridians
    ra_start = math.floor(view_ra[0] / ra_step_h) * ra_step_h
    ra_grid_vals = []
    v = ra_start
    while v <= view_ra[1] + ra_step_h / 2:
        ra_grid_vals.append(v)
        v += ra_step_h

    dec_lin = np.linspace(
        max(view_dec[0], -90), min(view_dec[1], 90), 200,
    )
    for ra_h in ra_grid_vals:
        lon = np.full(200, -np.radians(ra_h * 15 - 180))
        lat = np.radians(dec_lin)
        gx, gy = _mollweide_xy(lon, lat)
        ax.plot(gx, gy, color="gray", linewidth=0.4, alpha=0.5, zorder=1)

    # Dec parallels
    dec_start = math.floor(view_dec[0] / dec_step) * dec_step
    dec_grid_vals = []
    v = dec_start
    while v <= view_dec[1] + dec_step / 2:
        dec_grid_vals.append(v)
        v += dec_step

    ra_lin = np.linspace(view_ra[0], view_ra[1], 200)
    for dec_d in dec_grid_vals:
        lon = -np.radians(ra_lin * 15 - 180)
        lat = np.full(200, np.radians(dec_d))
        gx, gy = _mollweide_xy(lon, lat)
        ax.plot(gx, gy, color="gray", linewidth=0.4, alpha=0.5, zorder=1)

    # --- Panel outlines ---
    n = _N_EDGE_POINTS
    for ra_h, dec_d, half_ra, half_dec, name in panels_info:
        ra_l, ra_r = ra_h - half_ra, ra_h + half_ra
        dec_b, dec_t = dec_d - half_dec, dec_d + half_dec

        ra_pts = np.concatenate([
            np.linspace(ra_l, ra_r, n),
            np.full(n, ra_r),
            np.linspace(ra_r, ra_l, n),
            np.full(n, ra_l),
        ])
        dec_pts = np.concatenate([
            np.full(n, dec_b),
            np.linspace(dec_b, dec_t, n),
            np.full(n, dec_t),
            np.linspace(dec_t, dec_b, n),
        ])

        x, y = _mollweide_xy(
            -np.radians(ra_pts * 15 - 180),
            np.radians(dec_pts),
        )
        ax.plot(x, y, "-", linewidth=0.8, zorder=2)

        cx, cy = _mollweide_xy(
            np.array([-math.radians(ra_h * 15 - 180)]),
            np.array([math.radians(dec_d)]),
        )
        ax.text(
            cx[0], cy[0], name,
            fontsize=6, ha="center", va="center", zorder=3,
        )

    # --- View limits ---
    corners_ra = np.array([view_ra[0], view_ra[1], view_ra[0], view_ra[1]])
    corners_dec = np.array([view_dec[0], view_dec[0], view_dec[1], view_dec[1]])
    vx, vy = _mollweide_xy(
        -np.radians(corners_ra * 15 - 180),
        np.radians(corners_dec),
    )
    ax.set_xlim(min(vx), max(vx))
    ax.set_ylim(min(vy), max(vy))

    # --- Tick labels in RA / Dec ---
    center_dec_rad = np.radians((view_dec[0] + view_dec[1]) / 2)
    ra_tick_x, _ = _mollweide_xy(
        -np.radians(np.array(ra_grid_vals) * 15 - 180),
        np.full(len(ra_grid_vals), center_dec_rad),
    )
    ra_fmt = ".2f" if ra_step_h < 0.1 else ".1f" if ra_step_h < 1 else ".0f"
    ax.set_xticks(ra_tick_x)
    ax.set_xticklabels([f"{ra:{ra_fmt}}h" for ra in ra_grid_vals], fontsize=7)
    ax.set_xlabel("RA")

    center_ra_rad = -np.radians(
        ((view_ra[0] + view_ra[1]) / 2) * 15 - 180,
    )
    _, dec_tick_y = _mollweide_xy(
        np.full(len(dec_grid_vals), center_ra_rad),
        np.radians(np.array(dec_grid_vals)),
    )
    dec_fmt = ".2f" if dec_step < 0.5 else ".1f" if dec_step < 5 else ".0f"
    ax.set_yticks(dec_tick_y)
    ax.set_yticklabels([f"{d:{dec_fmt}}\u00b0" for d in dec_grid_vals], fontsize=7)
    ax.set_ylabel("Dec")

    ax.set_title(plan.get("plan_name", ""))

    return ax
