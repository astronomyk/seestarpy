from .connection import send_command

"""
To implement (params unknown):
"""

# def import_plan():
#     """
#     Import a plan to the Seestar.
#
#     .. note:: Parameters are unknown. Discovered via decompilation of the
#        Seestar APK v3.0.2, but no dedicated command class was found.
#
#     """
#     params = {'method': 'import_plan'}
#     return send_command(params)


# def clear_plan():
#     """
#     Clear a plan from the Seestar.
#
#     .. note:: Parameters are unknown. Discovered via decompilation of the
#        Seestar APK v3.0.2, but no dedicated command class was found.
#
#     """
#     params = {'method': 'clear_plan'}
#     return send_command(params)


def set_view_plan(plan):
    """
    Send an observation plan to the Seestar and start executing it.

    Parameters
    ----------
    plan : dict
        A plan dictionary with keys ``plan_name`` (str),
        ``update_time_seestar`` (str, format ``"yyyy.MM.dd"``), and
        ``list`` (list of target dicts). See the example below.

    Returns
    -------
    dict

    Notes
    -----
    Unlike :func:`~seestarpy.raw.iscope_start_view` which expects RA in
    **hour-angle**, the decompiled ``SetViewPlanCmd.java`` sends
    ``target_ra_dec`` directly without dividing RA by 15.  This suggests
    ``set_view_plan`` expects RA in **degrees**.

    Examples
    --------
    ::

        >>> from seestarpy import plan
        >>> my_plan = {
        ...     "plan_name": "Evening Session",
        ...     "update_time_seestar": "2026.02.23",
        ...     "list": [
        ...         {
        ...             "target_id": 12345,
        ...             "target_name": "M42",
        ...             "alias_name": "Orion Nebula",
        ...             "target_ra_dec": [83.82, -5.39],
        ...             "lp_filter": True,
        ...             "start_min": 0,
        ...             "duration_min": 30,
        ...         },
        ...         {
        ...             "target_id": 67890,
        ...             "target_name": "M31",
        ...             "alias_name": "Andromeda Galaxy",
        ...             "target_ra_dec": [10.68, 41.27],
        ...             "lp_filter": False,
        ...             "start_min": 30,
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


def clear_view_plan():
    """
    Stop and clear the currently executing observation plan.

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
        ...             "target_id": 11111,
        ...             "target_name": "NGC 7000",
        ...             "target_ra_dec": [314.75, 44.35],
        ...             "lp_filter": True,
        ...             "start_min": 0,
        ...             "duration_min": 60,
        ...         },
        ...     ],
        ... }
        >>> plan.set_plan(my_plan)

    """
    params = {'method': 'set_plan', 'params': plan}
    return send_command(params)


def get_plan(plan_name):
    """
    Retrieve a saved observation plan by name.

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
