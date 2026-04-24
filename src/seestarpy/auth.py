"""Firmware 7.18+ challenge-response authentication.

Seestar firmware 7.18 introduced a mandatory RSA challenge-response
handshake on port 4700.  The telescope sends a random challenge string;
the client must sign it with a private RSA key (SHA-1, PKCS#1 v1.5) and
return the base64-encoded signature.

The private key is the same for all devices — it is embedded inside ZWO's
Android APK (``libopenssllib.so``) and can be extracted with the
``extract_pem.py`` script from the ``seestar-api-research`` repository.

Key discovery order:

1. ``SEESTAR_KEY_PATH`` environment variable
2. ``seestar.pem`` in the current working directory
3. ``~/.seestarpy/seestar.pem``

If no key is found, authentication is silently skipped (backward-compatible
with older firmware that does not require it).

Signing uses the ``cryptography`` library when available
(``pip install seestarpy[auth]``), falling back to the ``openssl``
command-line tool.

Example::

    # Option A — set env var and let seestarpy find it automatically:
    #   export SEESTAR_KEY_PATH=/path/to/seestar.pem

    # Option B — place the key where auto-discovery finds it:
    #   cp seestar.pem ~/.seestarpy/seestar.pem

    # Option C — set at runtime:
    from seestarpy import auth
    auth.set_key_path("/path/to/seestar.pem")
"""

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path


class AuthenticationError(Exception):
    """Raised when telescope authentication fails."""


# ── Key discovery ────────────────────────────────────────────────────────────

def _discover_key_path():
    """Return the first key path that exists, or ``None``."""
    env = os.environ.get("SEESTAR_KEY_PATH")
    if env and Path(env).is_file():
        return env

    cwd = Path.cwd() / "seestar.pem"
    if cwd.is_file():
        return str(cwd)

    home = Path.home() / ".seestarpy" / "seestar.pem"
    if home.is_file():
        return str(home)

    return None


KEY_PATH = _discover_key_path()


def set_key_path(path):
    """Override the RSA key path at runtime.

    Parameters
    ----------
    path : str or Path
        Absolute or relative path to the PEM private key file.

    Raises
    ------
    FileNotFoundError
        If *path* does not point to an existing file.
    """
    global KEY_PATH
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Key file not found: {p}")
    KEY_PATH = str(p)


# ── RSA-SHA1 signing ─────────────────────────────────────────────────────────

def _sign_with_cryptography(key_path, challenge):
    """Sign *challenge* using the ``cryptography`` library."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    signature = private_key.sign(
        challenge.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA1(),
    )
    return base64.b64encode(signature).decode("ascii")


def _sign_with_openssl(key_path, challenge):
    """Sign *challenge* by shelling out to ``openssl``."""
    data_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dat")
    sig_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sig")
    try:
        data_tmp.write(challenge.encode("utf-8"))
        data_tmp.close()
        sig_tmp.close()

        result = subprocess.run(
            ["openssl", "dgst", "-sha1", "-sign", key_path,
             "-out", sig_tmp.name, data_tmp.name],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"openssl signing failed (rc={result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )

        with open(sig_tmp.name, "rb") as f:
            sig_bytes = f.read()

        return base64.b64encode(sig_bytes).decode("ascii")
    finally:
        os.unlink(data_tmp.name)
        os.unlink(sig_tmp.name)


def sign_challenge(key_path, challenge):
    """Sign a challenge string with RSA-SHA1 and return a base64 signature.

    Tries the ``cryptography`` library first, then falls back to the
    ``openssl`` command-line tool.

    Parameters
    ----------
    key_path : str
        Path to the PEM private key file.
    challenge : str
        The challenge string received from the telescope.

    Returns
    -------
    str
        Base64-encoded RSA-SHA1 signature.
    """
    try:
        return _sign_with_cryptography(key_path, challenge)
    except ImportError:
        pass

    try:
        return _sign_with_openssl(key_path, challenge)
    except FileNotFoundError:
        raise ImportError(
            "RSA signing requires either the 'cryptography' package "
            "(pip install seestarpy[auth]) or the 'openssl' CLI on PATH."
        )


# ── JSON-RPC helpers ─────────────────────────────────────────────────────────

_ID_GET_VERIFY = 1001
_ID_VERIFY = 1002
_ID_PI_VERIFIED = 1003


def _send_recv(sock, msg):
    """Send a JSON-RPC message and read one ``\\r\\n``-terminated response."""
    payload = json.dumps(msg) + "\r\n"
    sock.sendall(payload.encode())
    buf = ""
    while "\r\n" not in buf:
        chunk = sock.recv(4096).decode("utf-8")
        if not chunk:
            raise ConnectionError("Connection closed during auth handshake")
        buf += chunk
    return json.loads(buf.split("\r\n")[0])


async def _async_send_recv(reader, writer, msg):
    """Async version of :func:`_send_recv`."""
    payload = json.dumps(msg) + "\r\n"
    writer.write(payload.encode())
    await writer.drain()
    line = await reader.readuntil(separator=b"\r\n")
    return json.loads(line.decode().strip())


# ── Authentication handshake ─────────────────────────────────────────────────

def _run_handshake(send_recv, key_path):
    """Core handshake logic shared by sync and async paths.

    Parameters
    ----------
    send_recv : callable
        A function ``(msg_dict) -> response_dict``.
    key_path : str
        Path to the PEM private key.

    Returns
    -------
    bool
        ``True`` if authentication succeeded or was not required.

    Raises
    ------
    AuthenticationError
        If the telescope rejects the signature.
    """
    # Step 1 — request challenge
    resp = send_recv({
        "id": _ID_GET_VERIFY,
        "method": "get_verify_str",
        "params": "verify",
    })

    code = resp.get("code")
    if code == 103:
        # Method not found — old firmware, no auth needed.
        return True

    result = resp.get("result")
    challenge = result.get("str") if isinstance(result, dict) else result
    if not isinstance(challenge, str) or challenge == "":
        # No valid challenge — treat as old firmware.
        return True

    # Step 2 — sign and send
    sig = sign_challenge(key_path, challenge)

    resp = send_recv({
        "id": _ID_VERIFY,
        "method": "verify_client",
        "params": {"sign": sig, "data": challenge},
    })

    if resp.get("code") != 0:
        raise AuthenticationError(
            f"Telescope rejected verify_client (code={resp.get('code')}). "
            f"Your signing key may be stale or from an incompatible APK version. "
            f"Re-extract with: python -m seestarpy.extract_pem <path_to_apk>"
        )

    # Step 3 — confirm
    resp = send_recv({
        "id": _ID_PI_VERIFIED,
        "method": "pi_is_verified",
        "params": "verify",
    })
    if resp.get("code") != 0:
        # Non-fatal — matches behaviour of the official app.
        print(f"[auth] WARNING: pi_is_verified returned code={resp.get('code')} — proceeding")

    return True


def authenticate(sock, key_path=None):
    """Perform the 3-step auth handshake on a synchronous socket.

    Parameters
    ----------
    sock : socket.socket
        A connected TCP socket to the Seestar (port 4700).
    key_path : str, optional
        Path to the PEM key file.  Defaults to :data:`KEY_PATH`.

    Returns
    -------
    bool
        ``True`` if authentication succeeded or was not required.

    Raises
    ------
    AuthenticationError
        If the telescope rejects the client signature.
    """
    key_path = key_path or KEY_PATH
    if key_path is None:
        return True  # no key configured — skip auth

    def send_recv(msg):
        return _send_recv(sock, msg)

    return _run_handshake(send_recv, key_path)


async def authenticate_async(reader, writer, key_path=None):
    """Perform the 3-step auth handshake on an async connection.

    Parameters
    ----------
    reader : asyncio.StreamReader
    writer : asyncio.StreamWriter
    key_path : str, optional
        Path to the PEM key file.  Defaults to :data:`KEY_PATH`.

    Returns
    -------
    bool
        ``True`` if authentication succeeded or was not required.

    Raises
    ------
    AuthenticationError
        If the telescope rejects the client signature.
    """
    key_path = key_path or KEY_PATH
    if key_path is None:
        return True

    async def send_recv(msg):
        return await _async_send_recv(reader, writer, msg)

    # _run_handshake expects a plain callable, but send_recv is async.
    # Inline the steps here to keep things straightforward.

    # Step 1 — request challenge
    resp = await send_recv({
        "id": _ID_GET_VERIFY,
        "method": "get_verify_str",
        "params": "verify",
    })

    code = resp.get("code")
    if code == 103:
        return True

    result = resp.get("result")
    challenge = result.get("str") if isinstance(result, dict) else result
    if not isinstance(challenge, str) or challenge == "":
        return True

    # Step 2 — sign and send
    sig = sign_challenge(key_path, challenge)

    resp = await send_recv({
        "id": _ID_VERIFY,
        "method": "verify_client",
        "params": {"sign": sig, "data": challenge},
    })

    if resp.get("code") != 0:
        raise AuthenticationError(
            f"Telescope rejected verify_client (code={resp.get('code')}). "
            f"Your signing key may be stale or from an incompatible APK version. "
            f"Re-extract with: python -m seestarpy.extract_pem <path_to_apk>"
        )

    # Step 3 — confirm
    resp = await send_recv({
        "id": _ID_PI_VERIFIED,
        "method": "pi_is_verified",
        "params": "verify",
    })
    if resp.get("code") != 0:
        print(f"[auth] WARNING: pi_is_verified returned code={resp.get('code')} — proceeding")

    return True
