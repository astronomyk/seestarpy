from .connection import send_command
from .raw import iscope_get_app_state


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


def get_view_plan():
    """
    Get the currently executing observation plan and per-target state.

    .. warning:: On firmware v4.27 this returns ``code 103`` ("method not
       found") even while a plan is actively running.  Use
       :func:`~seestarpy.raw.iscope_get_app_state` instead and read
       ``result["ViewPlan"]`` for live plan state.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.get_view_plan()

    """
    params = {'method': 'get_view_plan'}
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


def clear_view_plan():
    """
    Stop and clear the currently executing observation plan.

    .. note:: The official Seestar app uses :func:`stop_view_plan`
       (``stop_func``) rather than ``clear_view_plan``.  Both appear to
       work on firmware v4.27, but prefer :func:`stop_view_plan` for
       compatibility with the official app's behaviour.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.clear_view_plan()

    """
    params = {'method': 'clear_view_plan'}
    return send_command(params)


def set_plan(plan):
    """
    Save an observation plan to the Seestar's device storage without
    executing it.

    .. warning:: On firmware v4.27 this returns ``code 200`` ("invalid id").
       The official app stores plans in its local SQLite database and never
       calls this endpoint.  The firmware may expect a numeric ``plan_id``
       rather than (or in addition to) ``plan_name``.  Use
       :func:`set_view_plan` to send and immediately execute a plan.

    .. note:: Inferred from decompilation of the Seestar APK v3.0.2.
       No dedicated command class was found; the parameter format is based
       on the ``PlanEntity`` data model and may differ on your firmware.

    Parameters
    ----------
    plan : dict
        A plan dictionary with keys ``plan_name`` (str),
        ``update_time_seestar`` (str, format ``"yyyy.MM.dd"``), and
        ``list`` (list of target dicts).  Same format as
        :func:`set_view_plan`.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> my_plan = {
        ...     "plan_name": "Tomorrow Night",
        ...     "update_time_seestar": "2026.02.24",
        ...     "list": [
        ...         {
        ...             "target_id": 987654321,
        ...             "target_name": "NGC 7000",
        ...             "target_ra_dec": [20.983, 44.35],
        ...             "lp_filter": True,
        ...             "start_min": 1260,
        ...             "duration_min": 60,
        ...         },
        ...     ],
        ... }
        >>> plan.set_plan(my_plan)  # NGC 7000 at 21:00 for 60 min

    """
    params = {'method': 'set_plan', 'params': plan}
    return send_command(params)


def get_plan(plan_name):
    """
    Retrieve a saved observation plan by name.

    .. warning:: On firmware v4.27, ``{plan_name: ...}`` returns an empty
       list.  Passing ``{plan_id: <int>}`` returns ``code 204``
       ("out of limit"), suggesting the firmware keys plans by numeric ID.
       The correct parameter format is unconfirmed.

    .. note:: Inferred from decompilation of the Seestar APK v3.0.2.
       No dedicated command class was found; the parameter format is based
       on the ``PlanEntity`` data model and may differ on your firmware.

    Parameters
    ----------
    plan_name : str
        The name of the saved plan to retrieve.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.get_plan("Tomorrow Night")

    """
    params = {'method': 'get_plan', 'params': {'plan_name': plan_name}}
    return send_command(params)


def list_plan():
    """
    List all saved observation plans on the Seestar.

    .. note:: On firmware v4.27 this is recognised by the firmware but
       returns an empty list even when a plan is running.  The official app
       stores plans in its local SQLite database.

    .. note:: Inferred from decompilation of the Seestar APK v3.0.2.
       No dedicated command class was found; the parameter format is based
       on the ``PlanEntity`` data model and may differ on your firmware.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.list_plan()

    """
    params = {'method': 'list_plan'}
    return send_command(params)


def delete_plan(plan_name):
    """
    Delete a saved observation plan from the Seestar.

    .. note:: On firmware v4.27, ``delete_plan`` with ``{plan_name: ...}``
       returned ``code 0`` (success) in testing, though it is unclear what
       was deleted since ``list_plan`` always returns empty.

    .. note:: Inferred from decompilation of the Seestar APK v3.0.2.
       No dedicated command class was found; the parameter format is based
       on the ``PlanEntity`` data model and may differ on your firmware.

    Parameters
    ----------
    plan_name : str
        The name of the saved plan to delete.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.delete_plan("Old Plan")

    """
    params = {'method': 'delete_plan', 'params': {'plan_name': plan_name}}
    return send_command(params)


def reset_plan(plan_name):
    """
    Reset progress on a saved observation plan so it can be re-executed
    from the beginning.

    .. warning:: On firmware v4.27 this returns ``code 200`` ("invalid id"),
       same as :func:`set_plan`.

    .. note:: Inferred from decompilation of the Seestar APK v3.0.2.
       No dedicated command class was found; the parameter format is based
       on the ``PlanEntity`` data model and may differ on your firmware.

    Parameters
    ----------
    plan_name : str
        The name of the saved plan to reset.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.reset_plan("Evening Session")

    """
    params = {'method': 'reset_plan', 'params': {'plan_name': plan_name}}
    return send_command(params)


def get_enabled_plan():
    """
    Get the currently enabled (active) observation plan.

    .. note:: On firmware v4.27 this is recognised by the firmware but
       returns an empty list even when a plan is running.  Use
       :func:`~seestarpy.raw.iscope_get_app_state` and read
       ``result["ViewPlan"]`` instead.

    .. note:: Inferred from decompilation of the Seestar APK v3.0.2.
       No dedicated command class was found; the parameter format is based
       on the ``PlanEntity`` data model and may differ on your firmware.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> plan.get_enabled_plan()

    """
    params = {'method': 'get_enabled_plan'}
    return send_command(params)
