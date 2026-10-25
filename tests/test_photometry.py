"""Unit tests for the photometry module and the firmware 9.x raw wrappers.

Payload shapes come from the decompiled Seestar app v3.4.1; the replies
mirror what firmware 9.75 returned on an S50 on 2026-10-25.
"""

from unittest.mock import patch, Mock

import pytest
import requests

from seestarpy import photometry as ph
from seestarpy import raw

OK = {"code": 0, "result": 0}


class TestPhotometryMode:
    @patch("seestarpy.photometry.send_command", return_value=OK)
    def test_enable_sets_capt_type(self, mock_send):
        ph.set_photometry_mode(True)
        assert mock_send.call_args[0][0] == {
            "method": "set_setting",
            "params": {"stack": {"capt_type": "photometry"}}}

    @patch("seestarpy.photometry.send_command", return_value=OK)
    def test_disable_restores_stack_and_passes_wide_cam(self, mock_send):
        ph.set_photometry_mode(False, wide_cam=True)
        assert mock_send.call_args[0][0]["params"] == {
            "stack": {"capt_type": "stack"}, "wide_cam": True}

    @pytest.mark.parametrize("capt, expected", [("photometry", True),
                                                ("stack", False)])
    @patch("seestarpy.photometry.send_command")
    def test_get_mode(self, mock_send, capt, expected):
        mock_send.return_value = {"code": 0,
                                  "result": {"stack": {"capt_type": capt}}}
        assert ph.get_photometry_mode() is expected

    @patch("seestarpy.photometry.send_command",
           return_value={"code": 103, "error": "method not found"})
    def test_get_mode_none_on_error(self, mock_send):
        assert ph.get_photometry_mode() is None


class TestCommands:
    @patch("seestarpy.photometry.send_command", return_value=OK)
    def test_check_photometry_defaults(self, mock_send):
        ph.check_photometry()
        assert mock_send.call_args[0][0] == {
            "method": "check_photometry",
            "params": {"magV": 10.0, "offsetDeg": 3.5}}

    @patch("seestarpy.photometry.send_command", return_value=OK)
    def test_photometry_stars_casts_id(self, mock_send):
        ph.get_photometry_stars("12")
        assert mock_send.call_args[0][0] == {
            "method": "get_photometry_stars", "params": {"image_id": 12}}

    @patch("seestarpy.photometry.send_command", return_value=OK)
    def test_record_and_stop(self, mock_send):
        ph.record_star("s1", name="V452 Vul")
        assert mock_send.call_args[0][0] == {
            "method": "set_photometry",
            "params": {"id": "s1", "save": True, "name": "V452 Vul"}}
        ph.stop_recording("s1")
        assert mock_send.call_args[0][0]["params"] == {"id": "s1",
                                                       "save": False}

    @patch("seestarpy.photometry.send_command", return_value=OK)
    def test_upload_refstar_info_wraps_list(self, mock_send):
        star = {"sourceId": "x", "raDeg": 1.0, "decDeg": 2.0, "magV": 9.0,
                "emagV": None, "photVariableFlag": "NOT_AVAILABLE"}
        ph.upload_refstar_info((star,))
        assert mock_send.call_args[0][0] == {
            "method": "upload_refstar_info", "params": {"refData": [star]}}

    @patch("seestarpy.photometry.send_command")
    def test_check_state_reads_view(self, mock_send):
        state = {"has_download_ref_star": False,
                 "ra_dec_deg_j2000": [300.2, 22.7]}
        mock_send.return_value = {"code": 0, "result": {
            "View": {"state": "working", "CheckPhotoMetry": state}}}
        assert ph.get_check_state() == state

    @patch("seestarpy.photometry.send_command",
           return_value={"code": 0, "result": {"FocuserMove": {}}})
    def test_check_state_none_without_view(self, mock_send):
        assert ph.get_check_state() is None


class TestLightCurve:
    PLOT = {"code": 0, "result": {"name": "V452 Vul", "save": True, "stars": [
        {"MJD": 61000.2, "measure_mag": 11.2, "err": 0.02, "snr": 50.0},
        {"MJD": 61000.1, "measure_mag": 11.1, "err": 0.02, "snr": 52.0,
         "radec_deg": [300.1, 22.6]},
    ]}}

    @patch("seestarpy.photometry.send_command")
    def test_sorted_by_mjd(self, mock_send):
        mock_send.return_value = self.PLOT
        pts = ph.light_curve("s1")
        assert mock_send.call_args[0][0] == {"method": "get_photometry_plot",
                                             "params": {"id": "s1"}}
        assert [p["MJD"] for p in pts] == [61000.1, 61000.2]

    @patch("seestarpy.photometry.send_command",
           return_value={"code": 207, "error": "fail to operate"})
    def test_empty_on_error(self, mock_send):
        assert ph.light_curve("s1") == []

    def test_save_light_curve(self, tmp_path):
        pts = ph._points(self.PLOT)
        out = tmp_path / "lc.csv"
        assert ph.save_light_curve(pts, out) == 2
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("MJD,measure_mag,err,snr")
        assert "300.1 22.6" in lines[1]

    @patch("seestarpy.photometry.send_command",
           return_value={"code": 0, "result": {"PhometryStars": [{"id": "a"}]}})
    def test_recorded_stars(self, mock_send):
        assert ph.recorded_stars() == [{"id": "a"}]


class TestWcs:
    REPLY = {"code": 0, "result": {
        "IMAGEW": 1080, "IMAGEH": 1920, "CRVAL1": 300.2, "CRVAL2": 22.7,
        "CRPIX1": 540.5, "CRPIX2": 960.5, "CD1_1": -0.0003, "CD1_2": 0.0,
        "CD2_1": 0.0, "CD2_2": 0.0003}}

    def test_header(self):
        hdr = ph.wcs_header(self.REPLY)
        assert hdr["CTYPE1"] == "RA---TAN" and hdr["CTYPE2"] == "DEC--TAN"
        assert hdr["NAXIS1"] == 1080 and hdr["NAXIS2"] == 1920
        assert hdr["CRVAL1"] == 300.2 and hdr["CD2_2"] == 0.0003

    def test_accepts_bare_result(self):
        assert ph.wcs_header(self.REPLY["result"])["CRPIX1"] == 540.5

    def test_no_image_raises(self):
        with pytest.raises(ValueError):
            ph.wcs_header({"code": 267, "error": "no image"})


APASS_TSV = """\
#RESOURCE=yCat_2336
#Name: II/336
RAJ2000\tDEJ2000\tVmag\te_Vmag
deg\tdeg\tmag\tmag
----------\t----------\t------\t------
300.087094\t+22.440065\t 8.117\t 0.000
299.251742\t+20.998419\t 6.790\t 0.031
bad\t+20.0\t 6.0\t 0.0
"""


class TestReferenceStars:
    def test_parse(self):
        stars = ph._parse_apass_tsv(APASS_TSV)
        assert len(stars) == 2
        assert stars[0] == {"sourceId": "APASS J300.08709+22.44007",
                            "raDeg": 300.087094, "decDeg": 22.440065,
                            "magV": 8.117, "emagV": None,
                            "photVariableFlag": "NOT_AVAILABLE"}
        assert stars[1]["emagV"] == 0.031

    @patch("seestarpy.photometry._requests.get")
    def test_query_params(self, mock_get):
        mock_get.return_value = Mock(text=APASS_TSV, raise_for_status=Mock())
        stars = ph.query_reference_stars(300.2, 22.7, radius_deg=2,
                                         mag_limit=11)
        q = mock_get.call_args.kwargs["params"]
        assert q["-source"] == "II/336/apass9"
        assert q["-c.rd"] == "2" and q["Vmag"] == "<11"
        assert len(stars) == 2

    @patch("seestarpy.photometry._requests.get",
           side_effect=requests.ConnectionError("down"))
    def test_query_connection_error(self, mock_get):
        with pytest.raises(ConnectionError):
            ph.query_reference_stars(0, 0)

    @patch("seestarpy.photometry.upload_refstar_info", return_value=OK)
    @patch("seestarpy.photometry.query_reference_stars", return_value=[{"x": 1}])
    @patch("seestarpy.photometry.get_check_state",
           return_value={"ra_dec_deg_j2000": [300.2, 22.7]})
    def test_provide_uses_field_centre(self, _state, mock_query, mock_upload):
        assert ph.provide_reference_stars() == OK
        assert mock_query.call_args[0] == (300.2, 22.7)
        mock_upload.assert_called_once_with([{"x": 1}])

    @patch("seestarpy.photometry.query_reference_stars")
    @patch("seestarpy.photometry.get_check_state", return_value=None)
    def test_provide_none_without_centre(self, _state, mock_query):
        assert ph.provide_reference_stars() is None
        mock_query.assert_not_called()


class TestRawFirmware9:
    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_get_dark_files(self, mock_send):
        raw.get_dark_files()
        assert mock_send.call_args[0][0] == {"method": "get_dark_files"}
        raw.get_dark_files("20s")
        assert mock_send.call_args[0][0]["params"] == {"name": "20s"}

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_set_dark_library(self, mock_send):
        raw.set_dark_library(False)
        assert mock_send.call_args[0][0] == {
            "method": "set_setting", "params": {"enable_dark_library": False}}

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_start_create_calib_frame(self, mock_send):
        raw.start_create_calib_frame()
        assert mock_send.call_args[0][0] == {
            "method": "start_create_calib_frame",
            "params": {"customer_library": True}}
        raw.start_create_calib_frame("dark", wide_cam=True,
                                     customer_library=False)
        assert mock_send.call_args[0][0]["params"] == {
            "customer_library": False, "wide_cam": True, "type": "dark"}

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_delete_image_accepts_str(self, mock_send):
        raw.delete_image("MyWorks/a.fit")
        assert mock_send.call_args[0][0] == {
            "method": "delete_image", "params": {"name": ["MyWorks/a.fit"]}}

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_fits_to_jpg(self, mock_send):
        raw.fits_to_jpg("MyWorks/a.fit")
        assert mock_send.call_args[0][0] == {
            "method": "fits_to_jpg", "params": {"name": "MyWorks/a.fit"}}

    @patch("seestarpy.raw.send_command", return_value=OK)
    def test_get_annotate_result(self, mock_send):
        raw.get_annotate_result()
        assert mock_send.call_args[0][0] == {"method": "get_annotate_result"}
        raw.get_annotate_result(file_path="MyWorks/a.fit")
        assert mock_send.call_args[0][0]["params"] == {
            "file_path": "MyWorks/a.fit"}

    @patch("seestarpy.raw.send_command")
    def test_get_capabilities(self, mock_send):
        mock_send.return_value = {"code": 0, "result": {"device": {
            "product_model": "Seestar S50", "firmware_ver_string": "9.75",
            "sn": "x", "can_dual_capture": False, "can_4k_quality": True}}}
        assert raw.get_capabilities() == {
            "product_model": "Seestar S50", "firmware_ver_string": "9.75",
            "can_dual_capture": False, "can_4k_quality": True}

    @patch("seestarpy.raw.send_command",
           return_value={"code": 103, "error": "method not found"})
    def test_get_capabilities_empty_on_error(self, mock_send):
        assert raw.get_capabilities() == {}
