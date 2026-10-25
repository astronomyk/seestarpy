"""Firmware 9.x additions: dark library, capabilities, photometry.

Read-only, except for the photometry-mode toggle which is restored.
Nothing here moves the mount.  Skips on firmware that predates a method
(``code 103``).
"""

import pytest

from seestarpy import photometry, raw

pytestmark = pytest.mark.integration


def _skip_if_unsupported(resp):
    if isinstance(resp, dict) and resp.get("code") == 103:
        pytest.skip(f"{resp.get('method')} not supported by this firmware")


def test_capabilities(verified_connection):
    caps = raw.get_capabilities()
    assert "product_model" in caps
    assert all(isinstance(v, bool) for k, v in caps.items()
               if k.startswith("can_"))


def test_dark_files(verified_connection):
    resp = raw.get_dark_files()
    _skip_if_unsupported(resp)
    assert resp["code"] == 0
    assert "list" in resp["result"]


def test_saved_photometry_stars(verified_connection):
    resp = photometry.get_saved_photometry_stars()
    _skip_if_unsupported(resp)
    assert resp["code"] == 0
    assert isinstance(photometry.recorded_stars(), list)


def test_photometry_mode_toggle(verified_connection):
    before = photometry.get_photometry_mode()
    try:
        assert photometry.set_photometry_mode(True)["code"] == 0
        assert photometry.get_photometry_mode() is True
    finally:
        photometry.set_photometry_mode(bool(before))
    assert photometry.get_photometry_mode() is bool(before)
