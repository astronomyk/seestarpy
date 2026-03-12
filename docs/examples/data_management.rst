Managing Files on the Seestar
=============================

The ``data`` module provides functions for listing, downloading, and
deleting files stored on the Seestar's internal eMMC storage.  Listing
uses the JSON-RPC API (port 4700), downloading uses the Seestar's
built-in HTTP server (port 80), and deletion uses SMB (port 445).


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

List individual files in a folder, optionally filtering by type:

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
The function returns the absolute path to the downloaded file.

If the file doesn't exist on the Seestar, a ``FileNotFoundError`` is
raised.  If the Seestar can't be reached, a ``ConnectionError`` is
raised.


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
    There is no undo.

.. code-block:: python

    data.delete_folder("M 81_sub")


Multi-Seestar usage
--------------------

All ``data`` functions support the ``ips`` keyword for multi-Seestar
operations:

.. code-block:: python

    from seestarpy import connection

    connection.find_available_ips(3)

    # List folders on all Seestars
    data.list_folders(ips="all")

    # Download from a specific Seestar
    data.download_file("M 81", "stack.fit", ips=2)
