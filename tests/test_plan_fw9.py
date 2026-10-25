"""Unit tests for the firmware 9.x plan additions (app v3.4.1 payloads)."""

from unittest.mock import patch

import pytest

from seestarpy import plan


def _plan(n=2):
    return {"plan_name": "t", "update_time_seestar": "2026.10.25",
            "list": [{"target_id": i, "target_name": f"T{i}",
                      "target_ra_dec": [1.0, 2.0], "start_min": 1320 + i,
                      "duration_min": 10} for i in range(n)]}


class TestConfigurePlan:
    def test_untouched_by_default(self):
        p = _plan()
        assert plan.configure_plan(p) == _plan()

    def test_all_keys(self):
        p = plan.configure_plan(
            _plan(), exposure_ms=20000, capt_type="photometry",
            tracking=True, camera_mode="dual", wide_exposure_ms=10000,
            wide_auto_exposure=False, wide_capt_type="stack",
            plan_target_af=True, viewplan_gohome=False)
        assert p["plan_target_af"] is True and p["viewplan_gohome"] is False
        for t in p["list"]:
            assert t["camera"] == {"exp_ms": {"stack_l": 20000},
                                   "stack": {"capt_type": "photometry"}}
            assert t["mount"] == {"tracking": True}
            assert t["camera_mode"] == "dual"
            assert t["second_camera"] == {
                "exp_ms": {"stack_l": 10000, "stack_l_auto": False},
                "stack": {"capt_type": "stack"}}

    def test_merges_into_existing_camera(self):
        p = _plan(1)
        p["list"][0]["camera"] = {"stack": {"capt_type": "stack"}}
        plan.configure_plan(p, exposure_ms=5000)
        assert p["list"][0]["camera"] == {"stack": {"capt_type": "stack"},
                                          "exp_ms": {"stack_l": 5000}}

    @pytest.mark.parametrize("kwargs", [{"camera_mode": "both"},
                                        {"capt_type": "trails"},
                                        {"wide_capt_type": "x"},
                                        {"exposure_ms": 0},
                                        {"wide_exposure_ms": -1}])
    def test_rejects_bad_values(self, kwargs):
        with pytest.raises(ValueError):
            plan.configure_plan(_plan(), **kwargs)


class TestPlanCommands:
    @patch("seestarpy.plan.send_command", return_value={"code": 0})
    def test_clear(self, mock_send):
        plan.clear_view_plan()
        assert mock_send.call_args[0][0] == {"method": "clear_view_plan"}

    @patch("seestarpy.plan.send_command", return_value={"code": 0})
    def test_restart(self, mock_send):
        plan.restart_view_plan(plan_target_af=True)
        assert mock_send.call_args[0][0] == {
            "method": "set_view_plan",
            "params": {"plan_target_af": True, "viewplan_gohome": True}}
