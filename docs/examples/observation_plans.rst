Observation Plans
=================

The ``plan`` module lets you send multi-target observation plans to the
Seestar.  The Seestar will autonomously slew to each target at the
scheduled time, plate-solve, and begin stacking — just like the official
app's "Plan" feature.


Quick example
-------------

.. code-block:: python

    from seestarpy import plan

    my_plan = {
        "plan_name": "Evening Session",
        "update_time_seestar": "2026.02.28",
        "list": [
            {
                "target_id": 100000001,
                "target_name": "M42",
                "alias_name": "Orion Nebula",
                "target_ra_dec": [5.588, -5.39],
                "lp_filter": True,
                "start_min": 1350,       # 22:30
                "duration_min": 30,
            },
            {
                "target_id": 100000002,
                "target_name": "M31",
                "alias_name": "Andromeda Galaxy",
                "target_ra_dec": [0.712, 41.27],
                "lp_filter": False,
                "start_min": 1380,       # 23:00
                "duration_min": 45,
            },
        ],
    }

    plan.set_view_plan(my_plan)

That's it — the Seestar will wait until 22:30 local time, slew to M42,
and start imaging.  At 23:00 it will move to M31 automatically.


Building a plan dictionary
--------------------------

A plan dictionary has three required keys:

``plan_name`` (str)
    A human-readable name for the plan.

``update_time_seestar`` (str)
    The date string in ``"yyyy.MM.dd"`` format (e.g. ``"2026.02.28"``).

``list`` (list of dicts)
    One dictionary per target, with the following fields:

    .. list-table::
       :header-rows: 1
       :widths: 20 10 70

       * - Field
         - Type
         - Description
       * - ``target_id``
         - int
         - A unique 9-digit integer identifier for each target.
       * - ``target_name``
         - str
         - Display name (e.g. ``"M 81"``).
       * - ``alias_name``
         - str
         - An alias, or ``""`` if unused.
       * - ``target_ra_dec``
         - list
         - ``[RA, Dec]`` — RA in decimal hours [0, 24), Dec in degrees [-90, 90].
       * - ``lp_filter``
         - bool
         - ``True`` to use the light-pollution filter for this target.
       * - ``start_min``
         - int
         - Start time as **minutes since local midnight** (see below).
       * - ``duration_min``
         - int
         - Observation duration in minutes.


Understanding ``start_min``
---------------------------

``start_min`` is the number of minutes after local midnight (00:00) on
the Seestar's internal clock.  It is **not** relative to when the plan
starts.

Some examples:

- 21:00 → ``1260``
- 22:30 → ``1350``
- 23:00 → ``1380``
- 00:00 (midnight) → ``1440``
- 01:30 AM → ``1530``

A helper to convert a ``(hours, minutes)`` tuple:

.. code-block:: python

    def to_start_min(hour, minute=0):
        """Convert a 24h time to start_min for a plan target."""
        return hour * 60 + minute

    to_start_min(22, 30)   # 1350
    to_start_min(1, 30)    # 90  — but for post-midnight, add 1440:
    1440 + to_start_min(1, 30)  # 1530

.. note::
    For targets scheduled after midnight, use values above 1440.
    The Seestar's clock is synced to the phone/host local time via
    ``raw.pi_set_time()``.


Monitoring a running plan
-------------------------

Use :func:`~seestarpy.plan.get_running_plan` to check the status of the
currently executing plan:

.. code-block:: python

    from seestarpy import plan

    vp = plan.get_running_plan()

    if vp is None:
        print("No plan is running")
    else:
        print(f"State: {vp['state']}")         # "working", "cancel", etc.
        print(f"Plan:  {vp['plan']['plan_name']}")

        # Per-target status (added by firmware)
        for target in vp["plan"]["list"]:
            name = target["target_name"]
            state = target.get("state", "pending")
            skip = target.get("skip", False)
            print(f"  {name}: {state}  (skip={skip})")

The firmware adds ``state``, ``lapse_ms``, and ``skip`` fields to each
target as the plan progresses.


Stopping a plan
---------------

.. code-block:: python

    plan.stop_view_plan()

This sends the same ``stop_func`` command that the official app uses.
After stopping, ``get_running_plan()`` will show the plan with
``state: "cancel"``.


Full workflow example
---------------------

A complete script that sets up the Seestar, submits a plan, monitors
progress, and then parks:

.. code-block:: python

    import time
    from seestarpy import raw, plan

    # Sync time and open the arm
    raw.pi_set_time()
    raw.scope_move_to_horizon()

    # Define a two-target plan
    tonight = {
        "plan_name": "Friday Night",
        "update_time_seestar": "2026.02.28",
        "list": [
            {
                "target_id": 200000001,
                "target_name": "M 81",
                "alias_name": "Bode's Galaxy",
                "target_ra_dec": [9.926, 69.065],
                "lp_filter": False,
                "start_min": 1260,       # 21:00
                "duration_min": 60,
            },
            {
                "target_id": 200000002,
                "target_name": "M 51",
                "alias_name": "Whirlpool Galaxy",
                "target_ra_dec": [13.498, 47.195],
                "lp_filter": False,
                "start_min": 1320,       # 22:00
                "duration_min": 90,
            },
        ],
    }

    # Send and start the plan
    plan.set_view_plan(tonight)

    # Poll until finished or cancelled
    while True:
        vp = plan.get_running_plan()
        if vp is None:
            break
        if vp["state"] != "working":
            print(f"Plan ended with state: {vp['state']}")
            break

        # Show progress
        for t in vp["plan"]["list"]:
            print(f"  {t['target_name']}: {t.get('state', 'pending')}")

        time.sleep(60)

    # Park when done
    raw.iscope_stop_view()
    raw.scope_park(True)
