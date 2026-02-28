CrowdSky Time-Block Stacking
============================

The ``crowdsky`` module automates the production of fixed-duration stacked
chunks from a Seestar observation session.  This enables citizen-science
time-domain astronomy by assembling a consistent, down-sampled dataset
from many Seestars.

Raw sub-frames are grouped into clock-aligned time blocks (default 15
minutes) and each block is batch-stacked independently on the Seestar.
Output files are renamed to a ``CrowdSky_*`` naming convention that
encodes the block boundary timestamp and filter, making re-runs fully
idempotent.


Discovering targets
-------------------

Use :func:`~seestarpy.crowdsky.list_targets` to see which observation
targets have raw sub-frames on the Seestar:

.. code-block:: python

    from seestarpy import crowdsky

    targets = crowdsky.list_targets()
    for t in targets:
        print(f"{t['target']:25s}  raw={t['raw_files']:>5d}  "
              f"stacked={t['stacked_files']:>3d}")

Example output::

    IC 434                     raw=  158  stacked=  1
    M 42                       raw=  216  stacked=  1
    M 81                       raw= 2053  stacked=  1


Previewing unstacked blocks
----------------------------

Use :func:`~seestarpy.crowdsky.find_unstacked_blocks` to see which
15-minute blocks still need stacking:

.. code-block:: python

    blocks = crowdsky.find_unstacked_blocks("IC 434")

    for b in blocks:
        start = b["block_start"].strftime("%H:%M")
        end = b["block_end"].strftime("%H:%M")
        print(f"  {start}-{end}  {b['frame_count']} frames  "
              f"{b['exposure']} {b['filter']}")

Example output::

    21:15-21:30  33 frames  10.0s LP
    21:30-21:45  69 frames  10.0s LP
    21:45-22:00  56 frames  10.0s LP


Dry run
-------

Use ``dry_run=True`` to preview what :func:`~seestarpy.crowdsky.stack_blocks`
would do without actually stacking:

.. code-block:: python

    result = crowdsky.stack_blocks("IC 434", dry_run=True)

Output::

    Dry run: 3 blocks to stack for IC 434
      21:15-21:30  33 frames x 10.0s (LP) = 330s
      21:30-21:45  69 frames x 10.0s (LP) = 690s
      21:45-22:00  56 frames x 10.0s (LP) = 560s


Stacking
--------

Run without ``dry_run`` to actually stack.  Each block is processed
sequentially (the Seestar can only do one batch stack at a time):

.. code-block:: python

    result = crowdsky.stack_blocks("IC 434")

Output::

    Stacking block 21:15-21:30 (33 frames, 10.0s LP)...
      Complete: 33 frames stacked
      Renamed -> CrowdSky_33_IC 434_10.0s_LP_20260227-211500.fit
    Stacking block 21:30-21:45 (69 frames, 10.0s LP)...
      Complete: 69 frames stacked
      Renamed -> CrowdSky_69_IC 434_10.0s_LP_20260227-213000.fit
    Stacking block 21:45-22:00 (56 frames, 10.0s LP)...
      Complete: 56 frames stacked
      Renamed -> CrowdSky_56_IC 434_10.0s_LP_20260227-214500.fit

The return value is a summary dict:

.. code-block:: python

    >>> result["blocks_stacked"]
    3
    >>> result["blocks_failed"]
    0

Re-running is safe --- already-stacked blocks are detected by their
``CrowdSky_*`` filenames and skipped automatically.


Output filename convention
--------------------------

Output files on the Seestar are renamed from the firmware's
``DSO_Stacked_*`` format to::

    CrowdSky_<N>_<target>_<exposure>_<filter>_<YYYYMMDD>-<HHMMSS>.fit

Where ``<YYYYMMDD>-<HHMMSS>`` is the **block boundary start time** (not
the stacking completion time).  For example::

    CrowdSky_33_IC 434_10.0s_LP_20260227-211500.fit
             ^^          ^^^^  ^^  ^^^^^^^^^^^^^^^
         frames      exposure filt  block start

This encoding makes coverage detection deterministic and idempotent,
even when multiple blocks have the same frame count.


Parameters
----------

``block_minutes`` (default 15)
    Duration of each time block in minutes.  Blocks are aligned to clock
    boundaries --- for 15-minute blocks, boundaries fall at ``:00``,
    ``:15``, ``:30``, and ``:45``.

``min_exptime`` (default 240)
    Minimum total effective exposure in seconds for a block to be worth
    stacking.  Calculated as ``frame_count * exposure_seconds``.  Blocks
    below this threshold are skipped.

.. code-block:: python

    # Use 10-minute blocks, skip blocks with less than 2 minutes of data
    result = crowdsky.stack_blocks("M 81", block_minutes=10, min_exptime=120)


Full workflow example
---------------------

A complete script that connects to a Seestar and processes all targets:

.. code-block:: python

    from seestarpy import connection, crowdsky

    connection.DEFAULT_IP = "192.168.1.83"

    # Discover targets
    for t in crowdsky.list_targets():
        print(f"\n--- {t['target']} ({t['raw_files']} raw frames) ---")
        result = crowdsky.stack_blocks(t["target"])
        print(f"Stacked: {result['blocks_stacked']}  "
              f"Failed: {result['blocks_failed']}  "
              f"Skipped: {result['blocks_skipped']}")
