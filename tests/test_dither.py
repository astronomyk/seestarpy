"""Unit tests for the dither controls in ui.py and status.pixel_scale.

Dithering matters for deep stacks: on an equatorially tracked field every
sub lands on the same pixels, so flat-field and dark residuals add
coherently instead of averaging down.  The firmware stores the throw in
pixels; ``ui.dither`` presents it in arcminutes, which means the
pixel<->arcmin conversion has to be right for both the S50 telephoto
(250 mm, 2.39 "/px) and the S30 Pro (160 mm, 3.74 "/px).
"""

import pytest
from unittest.mock import patch

from seestarpy import status, ui

ERR = {"jsonrpc": "2.0", "error": "method not found", "code": 103, "id": 1}


def _setting(pix=63, interval=5, enable=True, exp_ms=20000):
    return {"result": {"stack_dither": {"pix": pix, "interval": interval,
                                        "enable": enable},
                       "exp_ms": {"stack_l": exp_ms, "continuous": 500}},
            "code": 0}


def _device(focal_len=250.0):
    return {"result": {"device": {"focal_len": focal_len}}, "code": 0}


class TestPixelScale:
    @patch("seestarpy.raw.get_device_state", return_value=_device(250.0))
    def test_s50_telephoto(self, _m):
        assert status.pixel_scale() == pytest.approx(2.39, abs=0.01)

    @patch("seestarpy.raw.get_device_state", return_value=_device(160.0))
    def test_s30pro_wide(self, _m):
        """A different focal length must give a different plate scale."""
        assert status.pixel_scale() == pytest.approx(3.74, abs=0.01)

    def test_explicit_focal_length_skips_the_query(self):
        assert status.pixel_scale(250.0) == pytest.approx(2.39, abs=0.01)

    @patch("seestarpy.raw.get_device_state", return_value=ERR)
    def test_falls_back_when_device_unreadable(self, _m):
        assert status.pixel_scale() == status.DEFAULT_PIXEL_SCALE

    @patch("seestarpy.raw.get_device_state", return_value=_device(None))
    def test_falls_back_on_missing_focal_length(self, _m):
        assert status.pixel_scale() == status.DEFAULT_PIXEL_SCALE


class TestDitherGet:
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting(pix=63))
    def test_reports_arcmin_and_pixels(self, _s, _d):
        got = ui.dither()
        assert got["enabled"] is True
        assert got["radius_px"] == 63
        assert got["every_n_subs"] == 5
        # 63 px * 2.39 "/px / 60 = 2.51'
        assert got["radius_arcmin"] == pytest.approx(2.51, abs=0.02)

    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting(enable=False))
    def test_reports_disabled(self, _s, _d):
        assert ui.dither()["enabled"] is False

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_get_does_not_write(self, _s, _d, m_set):
        ui.dither()
        m_set.assert_not_called()


class TestDitherSet:
    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_radius_arcmin_converts_to_pixels(self, _s, _d, m_set):
        ui.dither(radius_arcmin=2.5)
        # 2.5' = 150" / 2.39 "/px = 62.8 -> 63 px
        assert m_set.call_args.kwargs["stack_dither"]["pix"] == 63

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device(160.0))
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_same_arcmin_gives_fewer_pixels_on_the_wide_camera(self, _s, _d, m_set):
        """The S30 Pro's coarser plate scale means fewer pixels per arcmin."""
        ui.dither(radius_arcmin=2.5)
        assert m_set.call_args.kwargs["stack_dither"]["pix"] == 40

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_configuring_implies_enabling(self, _s, _d, m_set):
        ui.dither(radius_arcmin=3)
        assert m_set.call_args.kwargs["stack_dither"]["enable"] is True

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_can_configure_while_staying_off(self, _s, _d, m_set):
        ui.dither(enabled=False, radius_arcmin=3)
        sent = m_set.call_args.kwargs["stack_dither"]
        assert sent["enable"] is False
        assert sent["pix"] == 75          # 3' still recorded

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_disable_preserves_pattern(self, _s, _d, m_set):
        """Turning it off must not silently reset radius/cadence."""
        ui.dither(False)
        sent = m_set.call_args.kwargs["stack_dither"]
        assert sent == {"pix": 63, "interval": 5, "enable": False}

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting(exp_ms=20000))
    def test_interval_seconds_converts_to_subs(self, _s, _d, m_set):
        """120 s at a 20 s sub + 1.5 s overhead -> every 6 subs."""
        ui.dither(interval_s=120)
        assert m_set.call_args.kwargs["stack_dither"]["interval"] == 6

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting(exp_ms=10000))
    def test_interval_seconds_tracks_exposure_time(self, _s, _d, m_set):
        """Same 120 s at a 10 s sub -> every 10 subs, not 6."""
        ui.dither(interval_s=120)
        assert m_set.call_args.kwargs["stack_dither"]["interval"] == 10

    @patch("seestarpy.raw.set_setting")
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_every_n_subs_passthrough(self, _s, _d, m_set):
        ui.dither(every_n_subs=6)
        assert m_set.call_args.kwargs["stack_dither"]["interval"] == 6


class TestDitherValidation:
    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_rejects_both_cadence_forms(self, _s, _d):
        with pytest.raises(ValueError, match="not both"):
            ui.dither(every_n_subs=5, interval_s=120)

    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_rejects_absurd_radius(self, _s, _d):
        with pytest.raises(ValueError, match="outside"):
            ui.dither(radius_arcmin=99)

    @patch("seestarpy.raw.get_device_state", return_value=_device())
    @patch("seestarpy.raw.get_setting", return_value=_setting())
    def test_rejects_zero_cadence(self, _s, _d):
        with pytest.raises(ValueError, match=">= 1"):
            ui.dither(every_n_subs=0)


class TestStatusBarDither:
    """The dashboard must make the dither state visible: a run that is
    silently dithering looks identical to one that is not."""

    @staticmethod
    def _dev(pix=63, enable=True):
        return {"result": {"setting": {"stack_dither": {"pix": pix,
                                                        "interval": 5,
                                                        "enable": enable}},
                           "device": {"focal_len": 250.0,
                                      "firmware_ver_string": "8.46"},
                           "mount": {}, "pi_status": {}, "storage": {}},
                "code": 0}

    @patch("seestarpy.raw.scope_get_equ_coord", return_value=ERR)
    @patch("seestarpy.raw.scope_get_horiz_coord", return_value=ERR)
    @patch("seestarpy.raw.iscope_get_app_state", return_value={"result": {}})
    def test_shows_amplitude_and_cadence_when_on(self, _a, _h, _e):
        with patch("seestarpy.raw.get_device_state", return_value=self._dev()):
            out = status.status_bar()
        assert "DITHER" in out
        assert "2.5'" in out

    @patch("seestarpy.raw.scope_get_equ_coord", return_value=ERR)
    @patch("seestarpy.raw.scope_get_horiz_coord", return_value=ERR)
    @patch("seestarpy.raw.iscope_get_app_state", return_value={"result": {}})
    def test_shows_off_when_disabled(self, _a, _h, _e):
        with patch("seestarpy.raw.get_device_state",
                   return_value=self._dev(enable=False)):
            out = status.status_bar()
        assert "off" in out

    @patch("seestarpy.raw.scope_get_equ_coord", return_value=ERR)
    @patch("seestarpy.raw.scope_get_horiz_coord", return_value=ERR)
    @patch("seestarpy.raw.get_device_state", return_value=ERR)
    @patch("seestarpy.raw.iscope_get_app_state", return_value={"result": {}})
    def test_no_crash_without_settings(self, *_m):
        assert isinstance(status.status_bar(), str)

    @patch("seestarpy.raw.scope_get_equ_coord", return_value=ERR)
    @patch("seestarpy.raw.scope_get_horiz_coord", return_value=ERR)
    @patch("seestarpy.raw.get_device_state", return_value=ERR)
    @patch("seestarpy.raw.iscope_get_app_state",
           return_value={"result": {"View": {"target_name": "x" * 40}}})
    def test_long_target_name_does_not_break_alignment(self, *_m):
        """Target names are user-set; an over-long one used to push the
        whole table out of alignment."""
        out = status.status_bar()
        widths = {len(ln) for ln in out.strip().splitlines()}
        assert len(widths) == 1, f"ragged table: {widths}"
