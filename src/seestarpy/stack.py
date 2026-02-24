from .connection import send_command
from .raw import iscope_get_app_state


def get_batch_stack_setting():
    """
    Get the current batch stack configuration.

    Returns the path and list of files currently configured for batch
    stacking.  The firmware enriches each file entry with ``date``,
    ``thn`` (thumbnail path), and ``type`` fields.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import stack
        >>> stack.get_batch_stack_setting()

    """
    params = {'method': 'get_batch_stack_setting'}
    return send_command(params)


def set_batch_stack_setting(path, files):
    """
    Configure which sub-frames to include in the next batch stack.

    This must be called before :func:`start_batch_stack`.  The files
    are FITS sub-frames stored on the Seestar's SD card.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Parameters
    ----------
    path : str
        Folder on the Seestar containing the sub-frames, e.g.
        ``"MyWorks/M 101_sub"``.  Use forward slashes.
    files : list[str]
        List of FITS filenames to stack.  Each filename follows the
        Seestar naming convention:
        ``Light_<target>_<exposure>_<filter>_<YYYYMMDD>-<HHMMSS>.fit``

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import stack
        >>> stack.set_batch_stack_setting(
        ...     path="MyWorks/M 101_sub",
        ...     files=[
        ...         "Light_M 101_10.0s_LP_20260120-061408.fit",
        ...         "Light_M 101_10.0s_LP_20260120-061345.fit",
        ...         "Light_M 101_10.0s_LP_20260120-061326.fit",
        ...     ],
        ... )

    """
    params = {
        'method': 'set_batch_stack_setting',
        'params': {
            'path': path,
            'files': [{'name': f} for f in files],
        },
    }
    return send_command(params)


def start_batch_stack():
    """
    Start batch stacking the files configured via
    :func:`set_batch_stack_setting`.

    Call :func:`set_batch_stack_setting` first to select the sub-frames.
    Monitor progress with :func:`get_batch_stack_status`.  When stacking
    completes, call :func:`clear_batch_stack` to reset the state.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import stack
        >>> stack.set_batch_stack_setting("MyWorks/M 101_sub", [
        ...     "Light_M 101_10.0s_LP_20260120-061408.fit",
        ...     "Light_M 101_10.0s_LP_20260120-061345.fit",
        ... ])
        >>> stack.start_batch_stack()

    """
    params = {'method': 'start_batch_stack'}
    return send_command(params)


def stop_batch_stack():
    """
    Stop a batch stack that is currently in progress.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import stack
        >>> stack.stop_batch_stack()

    """
    params = {'method': 'stop_batch_stack'}
    return send_command(params)


def clear_batch_stack():
    """
    Clear the batch stack state after stacking completes or is stopped.

    The official app sends this as ``clear_app_state`` with
    ``{"name": "BatchStack"}`` after a batch stack finishes.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Returns
    -------
    dict

    Examples
    --------
    ::

        >>> from seestarpy import stack
        >>> stack.clear_batch_stack()

    """
    params = {'method': 'clear_app_state', 'params': {'name': 'BatchStack'}}
    return send_command(params)


def get_batch_stack_status():
    """
    Return the current batch stack progress, or ``None`` if no batch
    stack is active.

    Queries ``iscope_get_app_state`` and extracts the ``BatchStack``
    key.

    .. note:: Confirmed via traffic capture from the official Seestar app
       v3.0.2 on 2026-02-24.

    Returns
    -------
    dict or None
        The ``BatchStack`` state dict when a batch stack has been run,
        or ``None`` if not present.  Key fields:

        - ``state`` (str): ``"working"``, ``"complete"``, ``"fail"``,
          or ``"cancel"``.
        - ``percent`` (float): Progress from 0 to 100.
        - ``stacked_img`` (int): Number of frames stacked so far.
        - ``total_img`` (int): Total frames to stack.
        - ``remaining_sec`` (int): Estimated seconds remaining.
        - ``output_file`` (dict): Present on completion, contains
          ``path`` and ``files`` with the output FITS and thumbnail.

    Examples
    --------
    ::

        >>> from seestarpy import stack
        >>> status = stack.get_batch_stack_status()
        >>> if status and status["state"] == "complete":
        ...     out = status["output_file"]["files"][0]["name"]
        ...     print(f"Stacked: {out}")

    """
    resp = iscope_get_app_state()
    result = resp.get("result")
    if isinstance(result, dict):
        return result.get("BatchStack")
    return None
