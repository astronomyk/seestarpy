"""Unit tests for ZWO plan sharing (app v3.4.1 share API).

Reply shapes mirror what api.seestar.com returned on 2026-11-04.
"""

import base64
import json
from unittest.mock import patch, Mock

import pytest
import requests

from seestarpy import plan


def _plan():
    return {"plan_name": "Evening", "update_time_seestar": "2026.11.04",
            "list": [
                {"target_id": 222222222, "target_name": "M 31",
                 "alias_name": "", "target_ra_dec": [0.712, 41.27],
                 "lp_filter": True, "start_min": 1380, "duration_min": 45,
                 "camera_mode": "dual"},
                {"target_id": 111111111, "target_name": "M 42",
                 "target_ra_dec": [5.588, -5.39], "start_min": 1320,
                 "duration_min": 30},
            ]}


def _reply(data, code=200, msg="OK"):
    return Mock(status_code=200, json=Mock(
        return_value={"code": code, "msg": msg, "data": data}))


class TestShareBody:
    def test_double_encoded_payload(self):
        body = plan._share_body(_plan())
        assert body["metadata"] == {"planName": "Evening", "targetCount": 2,
                                    "shootingDurationMinutes": 75}
        item = json.loads(body["payload"])
        assert item["name"] == "Evening" and item["operation"] == "update"
        assert item["recommendDurationMinute"] == 75
        assert json.loads(item["extra"]) == {"wideIncrementId": 0}
        targets = json.loads(item["payload"])
        assert [t["target_name"] for t in targets] == ["M 42", "M 31"]
        assert targets[0]["camera_mode"] == "tele"
        assert targets[0]["camera"] is None and targets[0]["mosaic"] is None
        assert targets[1]["camera_mode"] == "dual"
        assert targets[1]["lp_filter"] is True

    def test_keeps_configured_settings(self):
        p = plan.configure_plan(_plan(), capt_type="photometry")
        targets = json.loads(json.loads(plan._share_body(p)["payload"])
                             ["payload"])
        assert targets[0]["camera"] == {"stack": {"capt_type": "photometry"}}

    @pytest.mark.parametrize("change", [{"target_id": 0},
                                        {"target_name": " "},
                                        {"start_min": -5},
                                        {"duration_min": 0},
                                        {"target_ra_dec": [25.0, 0.0]},
                                        {"target_ra_dec": [1.0, 91.0]}])
    def test_rejects_unimportable_targets(self, change):
        p = _plan()
        p["list"][0].update(change)
        with pytest.raises(ValueError):
            plan._share_body(p)

    def test_rejects_empty_plan(self):
        with pytest.raises(ValueError):
            plan._share_body({"plan_name": "x", "list": []})


class TestShareRequests:
    @patch("seestarpy.plan._requests.request")
    def test_share_plan(self, mock_req):
        mock_req.return_value = _reply({
            "shareLink": "https://app.zwoastro.com/Seestar/plan?id=sh0xivw4",
            "shareId": "sh0xivw4"})
        assert plan.share_plan(_plan()) == {
            "share_id": "sh0xivw4",
            "share_link": "https://app.zwoastro.com/Seestar/plan?id=sh0xivw4"}
        args, kwargs = mock_req.call_args
        assert args == ("POST", "https://api.seestar.com/v1/share/plan")
        assert kwargs["headers"]["x-service-platform"] == "seestar"
        assert "payload" in kwargs["json"] and "metadata" in kwargs["json"]

    @pytest.mark.parametrize("prefix", ["", "data:image/png;base64,"])
    @patch("seestarpy.plan._requests.request")
    def test_share_plan_qrcode(self, mock_req, prefix, tmp_path):
        png = b"\x89PNG\r\n\x1a\nfake"
        mock_req.return_value = _reply(
            {"qrcode": prefix + base64.b64encode(png).decode()})
        out = tmp_path / "qr.png"
        assert plan.share_plan_qrcode(_plan(), path=out) == png
        assert out.read_bytes() == png
        assert mock_req.call_args[0][1].endswith("/v1/share/plan/qrcode")

    @patch("seestarpy.plan._requests.request")
    def test_api_error(self, mock_req):
        mock_req.return_value = Mock(status_code=400, json=Mock(
            return_value={"code": 100002, "msg": "Parameter error"}))
        with pytest.raises(RuntimeError, match="100002"):
            plan.share_plan(_plan())

    @patch("seestarpy.plan._requests.request",
           side_effect=requests.ConnectionError("down"))
    def test_connection_error(self, mock_req):
        with pytest.raises(ConnectionError):
            plan.share_plan(_plan())

    @patch("seestarpy.plan._requests.request")
    def test_get_shared_plan(self, mock_req):
        targets = [{"target_id": 1, "target_name": "M 42", "start_min": 1320,
                    "duration_min": 30, "target_ra_dec": [5.588, -5.39],
                    "camera": None, "mosaic": None, "camera_mode": "tele"}]
        item = {"id": "", "name": "shared", "payload": json.dumps(targets)}
        mock_req.return_value = _reply({
            "payload": json.dumps(item),
            "metadata": {"planName": "shared", "targetCount": 1,
                         "shootingDurationMinutes": 30}})
        p = plan.get_shared_plan(
            "https://app.zwoastro.com/Seestar/plan?id=sh0xivw4")
        assert mock_req.call_args[0] == (
            "GET", "https://api.seestar.com/v1/share/plan/sh0xivw4")
        assert p["plan_name"] == "shared"
        assert p["list"] == [{"target_id": 1, "target_name": "M 42",
                              "start_min": 1320, "duration_min": 30,
                              "target_ra_dec": [5.588, -5.39],
                              "camera_mode": "tele"}]

    @patch("seestarpy.plan._requests.request")
    def test_get_shared_plan_malformed(self, mock_req):
        mock_req.return_value = _reply({"payload": "not json"})
        with pytest.raises(ValueError):
            plan.get_shared_plan("sh0xivw4")


class TestParseShareId:
    @pytest.mark.parametrize("link", [
        "sh0xivw4",
        " https://app.zwoastro.com/Seestar/plan?id=sh0xivw4 ",
        "seestar://zwo.biz/Seestar/plan?id=sh0xivw4",
        "https://test-app.zwoastro.com/Seestar/plan?id=sh0xivw4&x=1"])
    def test_accepts(self, link):
        assert plan.parse_share_id(link) == "sh0xivw4"

    @pytest.mark.parametrize("link", [
        "", "a/b", "https://example.com/Seestar/plan?id=x",
        "https://app.zwoastro.com/Seestar/other?id=x",
        "https://app.zwoastro.com/Seestar/plan"])
    def test_rejects(self, link):
        with pytest.raises(ValueError):
            plan.parse_share_id(link)
