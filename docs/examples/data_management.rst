Managing Files on the Seestar
=============================

The ``data`` module lists, downloads, uploads, and deletes the files on
the Seestar's internal eMMC storage.  Observation folders live under
``MyWorks``: a target called ``M 81`` gets a ``M 81`` folder for stacked
results and a ``M 81_sub`` folder for the individual sub-frames.

Three different transports are involved, because no single one does
everything the firmware allows:

============  ======  =====================================================
Operation     Port    Protocol
============  ======  =====================================================
listing       4700    JSON-RPC — the same command socket as everything else
downloading   80      the Seestar's built-in HTTP server
uploading     445     SMB (needs ``pysmb``, a standard dependency)
deleting      445     SMB
============  ======  =====================================================

Listing over JSON-RPC is dramatically faster than the SMB directory walk
earlier versions used; downloading over HTTP is faster than SMB and needs
no authentication.


Listing folders and files
-------------------------

See what observation folders are on the Seestar:

.. code-block:: python

    from seestarpy import data

    folders = data.list_folders()
    for name, count in folders.items():
        print(f"{name}: {count} entries")

Example output::

    M 81: 3
    M 81_sub: 2053
    Lunar: 2

List individual files in a folder, optionally filtering by type.  The
returned dictionary maps file name to size in bytes — the firmware reports
in kilobytes, so the value is rounded to the nearest 1024:

.. code-block:: python

    # All files
    files = data.list_folder_contents("M 81")

    # Only FITS files
    fits = data.list_folder_contents("M 81_sub", filetype="fit")

    # Only thumbnails
    thumbs = data.list_folder_contents("M 81", filetype="thn.jpg")

    for name, size in list(fits.items())[:3]:
        print(f"{name}: {size / 1024:.0f} KB")

Available file type filters: ``"*"`` (all), ``"fit"``, ``"jpg"``,
``"thn.jpg"``, ``"*jpg"`` (all JPEGs).

.. warning::
    The listing API is **stateful per device**: the firmware keeps a single
    "current directory" cursor for each scope, which the listing sequence
    walks.  Two listing sequences running against the same scope at the
    same time interleave and silently return the wrong folder's contents —
    no error, just missing or mismatched files.  Never thread two listing
    calls to one Seestar, and don't run two scripts that list the same
    scope concurrently.  Different scopes in parallel are fine (that is
    what ``ips="all"`` does).


Downloading a single file
--------------------------

Use :func:`~seestarpy.data.download_file` to grab a specific file via
HTTP:

.. code-block:: python

    path = data.download_file(
        "M 81",
        "DSO_Stacked_33_M 81_20.0s_20260311_213509.fit",
        dest="./downloads",
    )
    print(f"Saved to: {path}")

The destination directory is created automatically if it doesn't exist.
The function returns the path to the downloaded file.

If the file doesn't exist on the Seestar, a ``FileNotFoundError`` is
raised.  If the Seestar can't be reached, a ``ConnectionError`` is
raised.

.. warning::
    **Verify sizes on a weak link.**  A marginal Wi-Fi connection makes the
    Seestar's HTTP server truncate a transfer *without* signalling an
    error: you get a short file, exit code zero, and a FITS that fails to
    open later.  Compare against the size the listing reported:

    .. code-block:: python

        import os

        sizes = data.list_folder_contents("M 81", filetype="fit")
        for name, remote_size in sizes.items():
            path = data.download_file("M 81", name, dest="./downloads")
            if os.path.getsize(path) < remote_size - 1024:
                print(f"TRUNCATED: {name} — retry this one")

    The ``- 1024`` slack matters: the listing reports kilobytes, so the
    "expected" size is only accurate to the nearest KB and an exact
    comparison would flag every healthy file.  A truncated transfer is short
    by megabytes, not bytes, so the tolerance costs you nothing.

    Moving the scope onto a wired connection (see
    :doc:`changing_seestar_settings`) fixes this properly.


Downloading an entire folder
-----------------------------

To download all files in a folder at once (via SMB):

.. code-block:: python

    data.download_folder("M 81", dest="./astro_data")

This prints progress as each file completes::

    Downloading 3 files from 'M 81' (45.2 MB)...
      [1/3] DSO_Stacked_33_M 81_20.0s_20260311_213509.fit (12.15 MB) OK
      [2/3] DSO_Stacked_33_M 81_20.0s_20260311_213509.jpg (5.32 MB) OK
      [3/3] DSO_Stacked_33_M 81_20.0s_20260311_213509_thn.jpg (0.03 MB) OK
    OK Download complete: 3 files

A night of sub-frames can be thousands of files and tens of gigabytes, so
a bulk download is a long job that will eventually be interrupted.  Write
the loop so re-running it resumes instead of starting over:

.. code-block:: python

    import os

    folder, dest = "M 81_sub", "./astro_data/M 81_sub"
    os.makedirs(dest, exist_ok=True)

    remote = data.list_folder_contents(folder, filetype="fit")
    for name, size in remote.items():
        local = os.path.join(dest, name)
        if os.path.exists(local) and os.path.getsize(local) >= size - 1024:
            continue                            # already have it, intact
        data.download_file(folder, name, dest=dest)

The size check is what makes this safe: a plain ``os.path.exists`` would
skip exactly the truncated files you most need to re-fetch.


Uploading files back to the Seestar
-----------------------------------

You can also push files *onto* the scope.  The main reason to do so is to
let the onboard stacker chew on sub-frames it no longer has — for example
re-stacking last month's subs with different settings after you cleared
the eMMC:

.. code-block:: python

    # Named files
    data.upload_files("NGC 3310_sub", [
        r"D:\subs\Light_NGC 3310_20.0s_IRCUT_20260709-232704.fit",
        r"D:\subs\Light_NGC 3310_20.0s_IRCUT_20260709-232728.fit",
    ])

    # Or a whole local directory
    data.upload_folder(r"D:\Seestar\NGC 3310", pattern="*.fit")

The destination folder under ``MyWorks`` is created if it does not exist;
``upload_folder`` defaults it to the base name of the local directory.
Sub-directories are ignored, because Seestar observation folders are flat.

Uploads are **idempotent**: a file already present remotely with a
matching byte size is skipped, so re-running after a dropped connection
resumes rather than re-sending everything.  Pass ``overwrite=True`` to
force it.

Both return ``{filename: bool}``, where ``True`` means the file is on the
scope after the call — whether it was just uploaded or was already there.

Once the subs are up, point the onboard batch stacker at them:

.. code-block:: python

    from seestarpy import stack

    files = list(data.list_folder_contents("NGC 3310_sub", filetype="fit"))
    stack.set_batch_stack_setting("MyWorks/NGC 3310_sub", files)
    stack.start_batch_stack()

See :doc:`crowdsky_stacking` for a workflow built on exactly this.


Deleting files
--------------

Delete specific files from a folder:

.. code-block:: python

    result = data.delete_files("M 81", [
        "old_stack.fit",
        "old_stack.jpg",
        "old_stack_thn.jpg",
    ])

    for name, ok in result.items():
        print(f"  {name}: {'deleted' if ok else 'not found'}")

Each filename maps to ``True`` (deleted) or ``False`` (not found or
failed).  Files that don't exist are silently skipped.


Deleting an entire folder
--------------------------

.. warning::
    This permanently removes data from the Seestar's internal storage.
    There is no undo, and no recycle bin on the eMMC.  Download and verify
    first.

.. code-block:: python

    data.delete_folder("M 81_sub")

Freeing space is worth doing deliberately — a full eMMC stops the scope
mid-run.  Check what you have left with:

.. code-block:: python

    from seestarpy import raw

    raw.get_disk_volume()


Multi-Seestar usage
--------------------

All ``data`` functions support the ``ips`` keyword for multi-Seestar
operations:

.. code-block:: python

    from seestarpy import connection as conn

    conn.discover()

    # List folders on all Seestars
    data.list_folders(ips="all")

    # Download from a specific Seestar
    data.download_file("M 81", "stack.fit", ips=2)

Each scope is handled on its own thread, and the result is keyed by IP.
Note that with ``ips="all"`` and a shared ``dest``, files with the same
name from different scopes will overwrite each other — give each scope its
own destination directory when you are collecting a fleet's output:

.. code-block:: python

    for name, ip in conn.AVAILABLE_IPS.items():
        data.download_folder("M 81", dest=f"./astro_data/{name}", ips=ip)
