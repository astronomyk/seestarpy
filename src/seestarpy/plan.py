import math
import random
import warnings
from datetime import datetime

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


def plot_mosaic_plan(plan, fov_width=0.75, fov_height=1.33, ax=None):
    """
    Plot panel borders of a mosaic plan on a Mollweide all-sky projection.

    Each panel is drawn as a closed rectangle in RA/Dec space, assuming an
    equatorial mount (panels axis-aligned).  This is useful for visually
    verifying the output of :func:`create_mosaic_plan` before sending it
    to the telescope.

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
        A Mollweide-projection axes to plot on.  If ``None``, a new figure
        and axes are created.

    Returns
    -------
    matplotlib.axes.Axes
        The axes with panel outlines and labels plotted.

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

    if ax is None:
        fig, ax = plt.subplots(subplot_kw={"projection": "mollweide"})

    ax.grid(True, alpha=0.3)

    for target in plan["list"]:
        ra_hours, dec_deg = target["target_ra_dec"]
        cos_dec = math.cos(math.radians(dec_deg))

        # Panel half-extents
        half_dec = fov_height / 2.0
        half_ra_hours = fov_width / (2.0 * 15.0 * cos_dec)

        dec_lo = dec_deg - half_dec
        dec_hi = dec_deg + half_dec
        ra_lo = ra_hours - half_ra_hours
        ra_hi = ra_hours + half_ra_hours

        # Build the four edges with interpolation for Mollweide curvature
        n = _N_EDGE_POINTS
        ra_pts = []
        dec_pts = []

        # Bottom edge: (ra_lo→ra_hi, dec_lo)
        ra_pts.extend(np.linspace(ra_lo, ra_hi, n))
        dec_pts.extend([dec_lo] * n)

        # Right edge: (ra_hi, dec_lo→dec_hi)
        ra_pts.extend([ra_hi] * n)
        dec_pts.extend(np.linspace(dec_lo, dec_hi, n))

        # Top edge: (ra_hi→ra_lo, dec_hi)
        ra_pts.extend(np.linspace(ra_hi, ra_lo, n))
        dec_pts.extend([dec_hi] * n)

        # Left edge: (ra_lo, dec_hi→dec_lo)
        ra_pts.extend([ra_lo] * n)
        dec_pts.extend(np.linspace(dec_hi, dec_lo, n))

        # Convert to Mollweide coordinates (radians)
        ra_arr = np.array(ra_pts)
        dec_arr = np.array(dec_pts)
        lon_rad = -np.radians(ra_arr * 15 - 180)
        lat_rad = np.radians(dec_arr)

        ax.plot(lon_rad, lat_rad, "-", linewidth=0.8)

        # Label at panel centre
        clon = -math.radians(ra_hours * 15 - 180)
        clat = math.radians(dec_deg)
        ax.text(
            clon, clat, target["target_name"],
            fontsize=6, ha="center", va="center",
        )

    ax.set_title(plan.get("plan_name", ""))

    return ax
