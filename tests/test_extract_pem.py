"""Unit tests for extract_pem.py — APK PEM extraction.

Ported from D:/Repos/seestar-tool/src/pem.rs test module.
"""

import io
import zipfile
from pathlib import Path

import pytest

from seestarpy.extract_pem import (
    extract_pem_from_apk,
    extract_pem_from_xapk,
    extract_strings,
    find_pem_keys,
    main,
)


FAKE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEA\n"
    "-----END PRIVATE KEY-----"
)

FAKE_KEY_2 = (
    "-----BEGIN PRIVATE KEY-----\n"
    "AAABBBCCC111222333\n"
    "-----END PRIVATE KEY-----"
)


def _make_apk(tmp_path: Path, name: str, files: dict[str, bytes]) -> Path:
    """Write a ZIP containing *files* to tmp_path/name and return the path."""
    apk = tmp_path / name
    with zipfile.ZipFile(apk, "w") as zf:
        for arcname, data in files.items():
            zf.writestr(arcname, data)
    return apk


# ---------------------------------------------------------------------------
# extract_strings
# ---------------------------------------------------------------------------

def test_extract_strings_empty_input():
    assert extract_strings(b"") == ""


def test_extract_strings_all_nonprintable():
    assert extract_strings(bytes([0x01, 0x02, 0x03, 0x80, 0xFF])) == ""


def test_extract_strings_includes_strings_of_four_or_more():
    assert "hello" in extract_strings(b"hello")


def test_extract_strings_excludes_runs_shorter_than_four():
    out = extract_strings(b"ab\x00cd\x00")
    assert "ab" not in out
    assert "cd" not in out


def test_extract_strings_splits_on_nonprintable():
    out = extract_strings(b"hello\x00world")
    assert "hello" in out
    assert "world" in out


def test_extract_strings_includes_trailing_run_without_terminator():
    assert "abcde" in extract_strings(b"\x00abcde")


def test_extract_strings_exactly_four_chars_is_included():
    assert "abcd" in extract_strings(b"\x00abcd\x00")


def test_extract_strings_three_chars_is_excluded():
    assert "abc" not in extract_strings(b"\x00abc\x00")


def test_extract_strings_space_is_printable():
    assert "ab cd" in extract_strings(b"ab cd")


# ---------------------------------------------------------------------------
# find_pem_keys
# ---------------------------------------------------------------------------

def test_find_pem_keys_no_keys():
    assert find_pem_keys("no keys here at all") == []


def test_find_pem_keys_begin_without_end_not_matched():
    assert find_pem_keys("-----BEGIN PRIVATE KEY-----\nMIIE\nno end marker") == []


def test_find_pem_keys_end_without_begin_not_matched():
    assert find_pem_keys("no begin marker\n-----END PRIVATE KEY-----") == []


def test_find_pem_keys_single_key():
    keys = find_pem_keys(FAKE_KEY)
    assert len(keys) == 1
    assert "BEGIN PRIVATE KEY" in keys[0]
    assert "END PRIVATE KEY" in keys[0]


def test_find_pem_keys_multiple_keys():
    keys = find_pem_keys(f"{FAKE_KEY}\nsome junk\n{FAKE_KEY_2}")
    assert len(keys) == 2


def test_find_pem_keys_surrounded_by_binary_noise():
    keys = find_pem_keys(f"junk before\n{FAKE_KEY}\njunk after")
    assert len(keys) == 1


def test_find_pem_keys_wrong_key_type_not_matched():
    # "RSA PRIVATE KEY" must not match the "PRIVATE KEY" regex.
    input_str = (
        "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"
    )
    assert find_pem_keys(input_str) == []


# ---------------------------------------------------------------------------
# extract_pem_from_apk
# ---------------------------------------------------------------------------

def test_extract_pem_from_apk_nonexistent_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_pem_from_apk("/nonexistent/path/to/pem_test.apk")


def test_extract_pem_from_apk_no_so_files_returns_empty(tmp_path):
    apk = _make_apk(tmp_path, "no_so.apk", {"assets/other.txt": b"nothing"})
    assert extract_pem_from_apk(apk) == []


def test_extract_pem_from_apk_so_with_no_key_returns_empty(tmp_path):
    apk = _make_apk(
        tmp_path,
        "no_key.apk",
        {"lib/arm64-v8a/libopenssllib.so": b"\x7fELF binary no key here"},
    )
    assert extract_pem_from_apk(apk) == []


def test_extract_pem_from_apk_arm64_so_with_key_returns_key(tmp_path):
    so_data = b"\x00\x01\x02" + FAKE_KEY.encode() + b"\x00"
    apk = _make_apk(
        tmp_path, "arm64.apk", {"lib/arm64-v8a/libopenssllib.so": so_data}
    )

    log: list[str] = []
    keys = extract_pem_from_apk(apk, progress=log.append)

    assert len(keys) == 1
    assert "BEGIN PRIVATE KEY" in keys[0]
    assert any("arm64-v8a" in line for line in log)


def test_extract_pem_from_apk_armeabi_so_with_key_returns_key(tmp_path):
    so_data = b"\x00" + FAKE_KEY.encode()
    apk = _make_apk(
        tmp_path,
        "armeabi.apk",
        {"lib/armeabi-v7a/libopenssllib.so": so_data},
    )
    assert len(extract_pem_from_apk(apk)) == 1


def test_extract_pem_from_apk_deduplicates_same_key_across_archs(tmp_path):
    so_data = b"\x00" + FAKE_KEY.encode()
    apk = _make_apk(
        tmp_path,
        "dedup.apk",
        {
            "lib/arm64-v8a/libopenssllib.so": so_data,
            "lib/armeabi-v7a/libopenssllib.so": so_data,
        },
    )
    assert len(extract_pem_from_apk(apk)) == 1


def test_extract_pem_from_apk_distinct_keys_across_archs_returns_both(tmp_path):
    apk = _make_apk(
        tmp_path,
        "two_keys.apk",
        {
            "lib/arm64-v8a/libopenssllib.so": b"\x00" + FAKE_KEY.encode(),
            "lib/armeabi-v7a/libopenssllib.so": b"\x00" + FAKE_KEY_2.encode(),
        },
    )
    assert len(extract_pem_from_apk(apk)) == 2


def test_extract_pem_from_apk_logs_scan_progress(tmp_path):
    so_data = b"\x00" + FAKE_KEY.encode()
    apk = _make_apk(
        tmp_path, "log.apk", {"lib/arm64-v8a/libopenssllib.so": so_data}
    )

    log: list[str] = []
    extract_pem_from_apk(apk, progress=log.append)

    assert any("Scanning" in line for line in log)
    assert any("Found" in line for line in log)


# ---------------------------------------------------------------------------
# helpers for XAPK (zip-of-apks)
# ---------------------------------------------------------------------------

def _apk_bytes(files: dict[str, bytes]) -> bytes:
    """Return the bytes of an APK (zip) containing *files*."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for arcname, data in files.items():
            zf.writestr(arcname, data)
    return buf.getvalue()


def _make_xapk(tmp_path, name: str, apks: dict[str, dict[str, bytes]]):
    """Write an XAPK (zip whose members are APKs) and return its path.

    *apks* maps the inner apk arcname (e.g. "config.arm64_v8a.apk") to that
    apk's own {arcname: bytes}. A dummy manifest.json is always included.
    """
    members = {apk: _apk_bytes(files) for apk, files in apks.items()}
    members["manifest.json"] = b"{}"
    return _make_apk(tmp_path, name, members)


# ---------------------------------------------------------------------------
# extract_pem_from_xapk
# ---------------------------------------------------------------------------

def test_extract_pem_from_xapk_nonexistent_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_pem_from_xapk("/nonexistent/path/to/app.xapk")


def test_extract_pem_from_xapk_key_in_abi_split_is_found(tmp_path):
    # The real v3.4.1 layout: base apk has no native lib; the key lives in
    # the arm64-v8a config split.
    so_data = b"\x00\x01\x02" + FAKE_KEY.encode() + b"\x00"
    xapk = _make_xapk(
        tmp_path,
        "seestar.xapk",
        {
            "base.apk": {"AndroidManifest.xml": b"x"},
            "config.arm64_v8a.apk": {
                "lib/arm64-v8a/libopenssllib.so": so_data
            },
        },
    )

    log: list[str] = []
    keys = extract_pem_from_xapk(xapk, progress=log.append)

    assert len(keys) == 1
    assert "BEGIN PRIVATE KEY" in keys[0]


def test_extract_pem_from_xapk_no_inner_apk_returns_empty(tmp_path):
    xapk = _make_apk(tmp_path, "empty.xapk", {"manifest.json": b"{}"})
    assert extract_pem_from_xapk(xapk) == []


def test_extract_pem_from_xapk_inner_apk_without_so_returns_empty(tmp_path):
    xapk = _make_xapk(
        tmp_path,
        "no_so.xapk",
        {"base.apk": {"assets/other.txt": b"nothing"}},
    )
    assert extract_pem_from_xapk(xapk) == []


def test_extract_pem_from_xapk_deduplicates_same_key_across_splits(tmp_path):
    so_data = b"\x00" + FAKE_KEY.encode()
    xapk = _make_xapk(
        tmp_path,
        "dedup.xapk",
        {
            "config.arm64_v8a.apk": {
                "lib/arm64-v8a/libopenssllib.so": so_data
            },
            "config.armeabi_v7a.apk": {
                "lib/armeabi-v7a/libopenssllib.so": so_data
            },
        },
    )
    assert len(extract_pem_from_xapk(xapk)) == 1


def test_extract_pem_from_xapk_distinct_keys_returns_both(tmp_path):
    xapk = _make_xapk(
        tmp_path,
        "two_keys.xapk",
        {
            "config.arm64_v8a.apk": {
                "lib/arm64-v8a/libopenssllib.so": b"\x00" + FAKE_KEY.encode()
            },
            "config.armeabi_v7a.apk": {
                "lib/armeabi-v7a/libopenssllib.so": b"\x00"
                + FAKE_KEY_2.encode()
            },
        },
    )
    assert len(extract_pem_from_xapk(xapk)) == 2


def test_extract_pem_from_xapk_inner_apk_in_subdirectory(tmp_path):
    # Guards the extract-to-tempdir / rebuild-path logic for a nested member.
    so_data = b"\x00" + FAKE_KEY.encode()
    xapk = _make_xapk(
        tmp_path,
        "subdir.xapk",
        {"apks/config.arm64_v8a.apk": {
            "lib/arm64-v8a/libopenssllib.so": so_data
        }},
    )
    assert len(extract_pem_from_xapk(xapk)) == 1


# ---------------------------------------------------------------------------
# main() routes .xapk to the xapk extractor
# ---------------------------------------------------------------------------

def test_main_routes_xapk_to_xapk_extractor(tmp_path, capsys):
    so_data = b"\x00" + FAKE_KEY.encode()
    xapk = _make_xapk(
        tmp_path,
        "cli.xapk",
        {"config.arm64_v8a.apk": {
            "lib/arm64-v8a/libopenssllib.so": so_data
        }},
    )
    rc = main([str(xapk), "--stdout", "--quiet"])
    assert rc == 0
    assert "BEGIN PRIVATE KEY" in capsys.readouterr().out
