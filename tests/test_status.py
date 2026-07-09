"""Unit tests for the status dashboard in status.py.

Regression coverage for the v8.x-firmware failure where ``status_bar``
crashed: it called ``scope_get_ra_dec`` (rejected on the command socket by
newer firmware), the error default ``["---", "---"]`` then hit
``round("---", ...)`` and raised ``TypeError``.  The fix switches to
``scope_get_equ_coord`` (valid on all firmware) and makes the numeric
formatting degrade to dashes instead of crashing.
"""

from unittest.mock import patch

from seestarpy import status

# A firmware "method not found" reply — no "result" key.
ERR = {"jsonrpc": "2.0", "error": "method not found", "code": 103, "id": 1}


class TestStatusBar:
    @patch("seestarpy.raw.scope_get_equ_coord", return_value=ERR)
    @patch("seestarpy.raw.scope_get_horiz_coord", return_value=ERR)
    @patch("seestarpy.raw.iscope_get_app_state", return_value=ERR)
    @patch("seestarpy.raw.get_device_state", return_value=ERR)
    def test_no_crash_when_every_endpoint_errors(self, *_mocks):
        """Every endpoint returns an error dict -> render dashes, don't crash."""
        out = status.status_bar()
        assert isinstance(out, str)
        assert "---" in out

    @patch("seestarpy.raw.scope_get_ra_dec")
    @patch("seestarpy.raw.scope_get_equ_coord",
           return_value={"result": [12.345, 45.678], "code": 0})
    @patch("seestarpy.raw.scope_get_horiz_coord",
           return_value={"result": [42.3, 312.7], "code": 0})
    @patch("seestarpy.raw.iscope_get_app_state", return_value={"result": {}})
    @patch("seestarpy.raw.get_device_state", return_value={"result": {}})
    def test_uses_equ_coord_not_ra_dec(self, m_dev, m_app, m_horiz,
                                       m_equ, m_radec):
        """RA/Dec is fetched via scope_get_equ_coord, not scope_get_ra_dec."""
        out = status.status_bar()
        assert isinstance(out, str)
        m_equ.assert_called()
        m_radec.assert_not_called()

    @patch("seestarpy.raw.scope_get_equ_coord",
           return_value={"result": [12.345, 45.678], "code": 0})
    @patch("seestarpy.raw.scope_get_horiz_coord",
           return_value={"result": [42.3, 312.7], "code": 0})
    @patch("seestarpy.raw.iscope_get_app_state", return_value={"result": {}})
    @patch("seestarpy.raw.get_device_state", return_value={"result": {}})
    def test_renders_numeric_coords_list_shape(self, m_dev, m_app, m_horiz, m_equ):
        """Older firmware: RA/Dec returned as a list [ra, dec]."""
        out = status.status_bar()
        assert "12.345" in out      # RA rounded to 3 dp
        assert "45.68" in out       # Dec rounded to 2 dp

    @patch("seestarpy.raw.scope_get_equ_coord",
           return_value={"result": {"ra": 12.345, "dec": 45.678}, "code": 0})
    @patch("seestarpy.raw.scope_get_horiz_coord",
           return_value={"result": [42.3, 312.7], "code": 0})
    @patch("seestarpy.raw.iscope_get_app_state", return_value={"result": {}})
    @patch("seestarpy.raw.get_device_state", return_value={"result": {}})
    def test_renders_numeric_coords_dict_shape(self, m_dev, m_app, m_horiz, m_equ):
        """Newer firmware: RA/Dec returned as {"ra":.., "dec":..} (regression
        for the KeyError:0 crash when indexing a dict like a list)."""
        out = status.status_bar()
        assert "12.345" in out
        assert "45.68" in out


class TestGetCoords:
    @patch("seestarpy.raw.scope_get_horiz_coord",
           return_value={"result": [42.3, 312.7], "code": 0})
    @patch("seestarpy.raw.scope_get_equ_coord",
           return_value={"result": [13.398, 54.925], "code": 0})
    def test_list_shape(self, m_equ, m_horiz):
        coords = status.get_coords()
        m_equ.assert_called()
        assert coords == {"ra": 13.398, "dec": 54.925,
                          "alt": 42.3, "az": 312.7}

    @patch("seestarpy.raw.scope_get_horiz_coord",
           return_value={"result": [42.3, 312.7], "code": 0})
    @patch("seestarpy.raw.scope_get_equ_coord",
           return_value={"result": {"ra": 13.398, "dec": 54.925}, "code": 0})
    def test_dict_shape(self, m_equ, m_horiz):
        """Newer firmware returns the equatorial coords as a dict."""
        coords = status.get_coords()
        assert coords == {"ra": 13.398, "dec": 54.925,
                          "alt": 42.3, "az": 312.7}

    @patch("seestarpy.raw.scope_get_horiz_coord", return_value=ERR)
    @patch("seestarpy.raw.scope_get_equ_coord", return_value=ERR)
    def test_raises_on_error(self, m_equ, m_horiz):
        import pytest
        with pytest.raises(ValueError):
            status.get_coords()
