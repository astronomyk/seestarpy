CrowdSky Time-Block Stacking
============================

The ``crowdsky`` module automates the production of fixed-duration stacked
chunks from a Seestar observation session.  This enables citizen-science
time-domain astronomy by assembling a consistent, down-sampled dataset
from many Seestars.

Raw sub-frames are grouped into clock-aligned time blocks (default 15
minutes) and each block is batch-stacked independently on the Seestar.
Output files are renamed to a ``CrowdSky_*`` naming convention that
encodes the UTC chunk key, HEALPix sky pixel, and filter, making re-runs
fully idempotent.


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
      Renamed -> CrowdSky_33_IC 434_10.0s_LP_20260227.81_HP049152.fit
    Stacking block 21:30-21:45 (69 frames, 10.0s LP)...
      Complete: 69 frames stacked
      Renamed -> CrowdSky_69_IC 434_10.0s_LP_20260227.82_HP049152.fit
    Stacking block 21:45-22:00 (56 frames, 10.0s LP)...
      Complete: 56 frames stacked
      Renamed -> CrowdSky_56_IC 434_10.0s_LP_20260227.83_HP049152.fit

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

    CrowdSky_<N>_<target>_<exposure>_<filter>_<YYYYMMDD.CC>_HP<nnnnnn>.fit

Where:

- ``<YYYYMMDD.CC>`` is the **UTC chunk key** — the UTC date plus a
  chunk index (0--95) representing which 15-minute slot of the day the
  block falls in.
- ``HP<nnnnnn>`` is the **HEALPix pixel** (NSIDE=64, nested) derived
  from the RA/Dec in the stacked FITS header.  This encodes the sky
  position so that stacks from different Seestars pointing at the same
  area can be matched.  If RA/Dec cannot be read, it falls back to
  ``HP000000``.

For example::

    CrowdSky_33_IC 434_10.0s_LP_20260227.81_HP049152.fit
             ^^          ^^^^  ^^  ^^^^^^^^^^  ^^^^^^^^
         frames      exposure filt  UTC chunk   HEALPix

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


Stacking all targets at once
-----------------------------

Use :func:`~seestarpy.crowdsky.stack_all` to process every target that
has raw sub-frames, without having to name them individually:

.. code-block:: python

    result = crowdsky.stack_all(dry_run=True)    # preview first
    result = crowdsky.stack_all()                # then run

    print(f"Stacked: {result['total_blocks_stacked']}  "
          f"Failed: {result['total_blocks_failed']}  "
          f"Skipped: {result['total_blocks_skipped']}  "
          f"across {result['targets_processed']} targets")

The same ``block_minutes``, ``min_exptime``, and ``dry_run`` parameters
are passed through to each target.


Purging CrowdSky stacks
-------------------------

If you need to re-stack from scratch (e.g. after changing block size),
use :func:`~seestarpy.crowdsky.purge_crowdsky_stacks` to delete all
``CrowdSky_*`` files from the Seestar:

.. code-block:: python

    # Purge one target
    crowdsky.purge_crowdsky_stacks("IC 434")

    # Purge all targets
    crowdsky.purge_crowdsky_stacks()

After purging, :func:`~seestarpy.crowdsky.stack_blocks` will see all
blocks as unstacked again.


CrowdSky server
---------------

The ``crowdsky`` module also supports uploading stacked chunks to a
CrowdSky collaboration server for aggregation with other observers.

.. code-block:: python

    from seestarpy import crowdsky

    # Set your credentials
    crowdsky.set_credentials("username", "password")

    # Upload a stacked FITS file
    crowdsky.upload_stack("CrowdSky_33_IC 434_10.0s_LP_20260227.81_HP049152.fit")

    # List your uploaded stacks
    stacks = crowdsky.list_stacks()
    for s in stacks:
        print(s)

    # Download stacks by chunk key
    crowdsky.download_stack(["20260227.81_HP049152"], dest="./downloads")


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
