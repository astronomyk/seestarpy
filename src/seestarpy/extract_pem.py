"""Extract PEM private keys from native libraries inside an APK.

A general-purpose utility: given an APK file, scan its bundled native
libraries (``lib/*/libopenssllib.so``) with a ``strings(1)``-style pass
and report any ``-----BEGIN PRIVATE KEY-----`` blocks found.

CLI usage::

    python -m seestarpy.extract_pem <apk_path>

By default writes the first extracted key to ``~/.seestarpy/seestar.pem``,
which is where :mod:`seestarpy.auth` auto-discovers it. Pass ``--stdout``
to print keys instead, or ``-o PATH`` to override the output location.

This module ships no key. Users supply their own APK.
"""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path


SO_PATHS = (
    "lib/arm64-v8a/libopenssllib.so",
    "lib/armeabi-v7a/libopenssllib.so",
)

PEM_RE = re.compile(
    r"-----BEGIN PRIVATE KEY-----[\s\S]*?-----END PRIVATE KEY-----"
)

DEFAULT_OUTPUT = Path.home() / ".seestarpy" / "seestar.pem"


def extract_strings(data: bytes) -> str:
    """Return printable-ASCII runs of length >= 4, separated by newlines.

    Mirrors the Unix ``strings(1)`` utility with a 4-char threshold.
    Printable is defined as ``0x20`` (space) through ``0x7e`` (tilde).
    """
    runs = []
    cur = bytearray()
    for b in data:
        if 0x20 <= b <= 0x7e:
            cur.append(b)
            continue
        if len(cur) >= 4:
            runs.append(cur.decode("ascii"))
        cur.clear()
    if len(cur) >= 4:
        runs.append(cur.decode("ascii"))
    return "\n".join(runs)


def find_pem_keys(dump: str) -> list[str]:
    """Return every ``BEGIN PRIVATE KEY`` / ``END PRIVATE KEY`` block in dump."""
    return PEM_RE.findall(dump)


def extract_pem_from_apk(apk_path, progress=None) -> list[str]:
    """Extract all PEM private keys from the native libs of an APK.

    Parameters
    ----------
    apk_path : str or Path
        Path to an ``.apk`` file.
    progress : callable, optional
        One-arg callback invoked with human-readable status strings.
        Defaults to a no-op.

    Returns
    -------
    list of str
        Deduplicated, sorted list of PEM blocks. Empty if no
        ``libopenssllib.so`` is present or no key is embedded.
    """
    apk_path = Path(apk_path)
    if not apk_path.is_file():
        raise FileNotFoundError(f"APK not found: {apk_path}")

    log = progress or (lambda _msg: None)

    keys: set[str] = set()
    with zipfile.ZipFile(apk_path) as zf:
        names = set(zf.namelist())
        found = [p for p in SO_PATHS if p in names]
        if not found:
            log(
                f"No libopenssllib.so found. Looked in: {', '.join(SO_PATHS)}"
            )
            return []

        for so_path in found:
            log(f"Scanning {so_path}...")
            data = zf.read(so_path)
            dump = extract_strings(data)
            found_keys = find_pem_keys(dump)
            log(f"  Found {len(found_keys)} key(s) in {Path(so_path).name}")
            keys.update(found_keys)

    return sorted(keys)


def write_key(pem: str, out_path=DEFAULT_OUTPUT) -> Path:
    """Write a PEM string to disk with owner-only permissions on POSIX."""
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(pem)
    try:
        out_path.chmod(0o600)
    except OSError:
        pass
    return out_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m seestarpy.extract_pem",
        description=(
            "Extract a PEM private key from a Seestar APK's libopenssllib.so "
            "and write it to ~/.seestarpy/seestar.pem, where seestarpy will "
            "auto-discover it."
        ),
    )
    parser.add_argument("apk", help="Path to the .apk file")
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print key(s) to stdout instead of writing to a file",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress output"
    )
    args = parser.parse_args(argv)

    progress = (lambda _m: None) if args.quiet else (lambda m: print(m, file=sys.stderr))

    try:
        keys = extract_pem_from_apk(args.apk, progress=progress)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except zipfile.BadZipFile:
        print(f"error: not a valid APK/ZIP: {args.apk}", file=sys.stderr)
        return 2

    if not keys:
        print(
            "error: found no PEM private key in APK native libraries. "
            "Either the APK is not a Seestar APK or its format has changed.",
            file=sys.stderr,
        )
        return 1

    if args.stdout:
        for pem in keys:
            print(pem)
        return 0

    out = write_key(keys[0], args.output)
    print(f"Wrote key to {out}", file=sys.stderr)
    if len(keys) > 1:
        print(
            f"note: {len(keys)} distinct keys found; wrote the first. "
            "Use --stdout to see all.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
