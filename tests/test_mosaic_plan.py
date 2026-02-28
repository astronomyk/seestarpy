"""Unit tests for create_mosaic_plan() in plan.py."""

import math
from unittest.mock import patch

import pytest

from seestarpy.plan import _generate_target_ids, create_mosaic_plan


# ---------------------------------------------------------------------------
# _generate_target_ids
# ---------------------------------------------------------------------------

class TestGenerateTargetIds:
    def test_correct_count(self):
        ids = _generate_target_ids(10)
        assert len(ids) == 10

    def test_all_nine_digits(self):
        ids = _generate_target_ids(20)
        for tid in ids:
            assert 100_000_000 <= tid <= 999_999_999

    def test_all_unique(self):
        ids = _generate_target_ids(50)
        assert len(set(ids)) == 50


# ---------------------------------------------------------------------------
# create_mosaic_plan — basic grid geometry
# ---------------------------------------------------------------------------

class TestSinglePanel:
    def test_width_zero_height_zero(self):
        """width=0, height=0 should produce exactly 1 panel at centre."""
        result = create_mosaic_plan(
            plan_name="Single",
            center_ra=10.0,
            center_dec=30.0,
            width=0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        assert len(result["list"]) == 1
        panel = result["list"][0]
        assert panel["target_ra_dec"][0] == pytest.approx(10.0)
        assert panel["target_ra_dec"][1] == pytest.approx(30.0)
        assert panel["duration_min"] == 60


class TestGrid2x2:
    def test_panel_count(self):
        """A 2x2 grid should produce 4 panels."""
        result = create_mosaic_plan(
            plan_name="2x2",
            center_ra=12.0,
            center_dec=0.0,
            width=2.0,
            height=2.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        assert len(result["list"]) == 4

    def test_duration_split(self):
        """Total time should be divided equally among panels."""
        result = create_mosaic_plan(
            plan_name="2x2",
            center_ra=12.0,
            center_dec=0.0,
            width=2.0,
            height=2.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        for panel in result["list"]:
            assert panel["duration_min"] == 30  # 120 // 4


class TestBoustrophedonOrder:
    def test_row1_reversed_vs_row0(self):
        """Odd Dec rows should traverse RA in the opposite direction."""
        result = create_mosaic_plan(
            plan_name="Snake",
            center_ra=12.0,
            center_dec=0.0,
            width=3.0,
            height=2.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=180,
            start_min=1320,
        )
        panels = result["list"]
        # 3 RA x 2 Dec = 6 panels
        assert len(panels) == 6

        # Row 0 (lower dec): RA should increase
        row0_ra = [panels[i]["target_ra_dec"][0] for i in range(3)]
        assert row0_ra == sorted(row0_ra)

        # Row 1 (higher dec): RA should decrease
        row1_ra = [panels[i]["target_ra_dec"][0] for i in range(3, 6)]
        assert row1_ra == sorted(row1_ra, reverse=True)


class TestCosDecCorrection:
    def test_ra_spacing_doubles_at_dec60(self):
        """At dec=60°, cos(60°)=0.5 so RA spacing (in hours) is 2x equator."""
        equator = create_mosaic_plan(
            plan_name="Eq",
            center_ra=12.0,
            center_dec=0.0,
            width=2.0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        dec60 = create_mosaic_plan(
            plan_name="D60",
            center_ra=12.0,
            center_dec=60.0,
            width=2.0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        # RA step in hours at equator
        eq_step = abs(
            equator["list"][1]["target_ra_dec"][0]
            - equator["list"][0]["target_ra_dec"][0]
        )
        # RA step in hours at dec=60
        d60_step = abs(
            dec60["list"][1]["target_ra_dec"][0]
            - dec60["list"][0]["target_ra_dec"][0]
        )
        # cos(60°) = 0.5, so d60_step should be ~2x eq_step
        assert d60_step == pytest.approx(2.0 * eq_step, rel=1e-6)


class TestSequentialScheduling:
    def test_each_panel_starts_after_previous(self):
        """Panels should be scheduled sequentially without overlap."""
        result = create_mosaic_plan(
            plan_name="Seq",
            center_ra=12.0,
            center_dec=0.0,
            width=3.0,
            height=2.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=180,
            start_min=1320,
        )
        panels = result["list"]
        for i in range(1, len(panels)):
            prev_end = panels[i - 1]["start_min"] + panels[i - 1]["duration_min"]
            assert panels[i]["start_min"] == prev_end


class TestUniqueTargetIds:
    def test_all_ids_unique_and_nine_digits(self):
        result = create_mosaic_plan(
            plan_name="IDs",
            center_ra=12.0,
            center_dec=0.0,
            width=5.0,
            height=5.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=300,
            start_min=1320,
        )
        ids = [p["target_id"] for p in result["list"]]
        assert len(ids) == len(set(ids))
        for tid in ids:
            assert 100_000_000 <= tid <= 999_999_999


class TestPanelNaming:
    def test_zero_padded_with_prefix(self):
        result = create_mosaic_plan(
            plan_name="Names",
            center_ra=12.0,
            center_dec=0.0,
            width=2.0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
            target_name_prefix="NGC7000",
        )
        assert result["list"][0]["target_name"] == "NGC7000_01"
        assert result["list"][1]["target_name"] == "NGC7000_02"

    def test_default_prefix(self):
        result = create_mosaic_plan(
            plan_name="Default",
            center_ra=12.0,
            center_dec=0.0,
            width=0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        assert result["list"][0]["target_name"] == "Mosaic_01"


class TestPlanDictSchema:
    def test_required_keys_present(self):
        result = create_mosaic_plan(
            plan_name="Schema",
            center_ra=12.0,
            center_dec=0.0,
            width=1.0,
            height=1.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        assert "plan_name" in result
        assert "update_time_seestar" in result
        assert "list" in result
        assert result["plan_name"] == "Schema"

    def test_date_format(self):
        result = create_mosaic_plan(
            plan_name="Date",
            center_ra=12.0,
            center_dec=0.0,
            width=0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        # Format: "YYYY.MM.DD"
        date_str = result["update_time_seestar"]
        parts = date_str.split(".")
        assert len(parts) == 3
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2
        assert len(parts[2]) == 2

    def test_target_dict_fields(self):
        result = create_mosaic_plan(
            plan_name="Fields",
            center_ra=12.0,
            center_dec=0.0,
            width=0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        target = result["list"][0]
        required_keys = {
            "target_id", "target_name", "alias_name",
            "target_ra_dec", "lp_filter", "start_min", "duration_min",
        }
        assert required_keys.issubset(target.keys())
        assert isinstance(target["target_ra_dec"], list)
        assert len(target["target_ra_dec"]) == 2


class TestLpFilterPropagated:
    def test_lp_filter_true(self):
        result = create_mosaic_plan(
            plan_name="LP",
            center_ra=12.0,
            center_dec=0.0,
            width=2.0,
            height=2.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
            lp_filter=True,
        )
        for panel in result["list"]:
            assert panel["lp_filter"] is True

    def test_lp_filter_false_default(self):
        result = create_mosaic_plan(
            plan_name="NoLP",
            center_ra=12.0,
            center_dec=0.0,
            width=2.0,
            height=2.0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        for panel in result["list"]:
            assert panel["lp_filter"] is False


class TestRaWrapAround:
    def test_ra_stays_in_range(self):
        """Panels near RA=0h should wrap to stay in [0, 24)."""
        result = create_mosaic_plan(
            plan_name="Wrap",
            center_ra=0.1,
            center_dec=0.0,
            width=3.0,
            height=0,
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        for panel in result["list"]:
            ra = panel["target_ra_dec"][0]
            assert 0 <= ra < 24, f"RA {ra} out of [0, 24)"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_center_ra_low(self):
        with pytest.raises(ValueError, match="center_ra"):
            create_mosaic_plan("X", -1, 0, 1, 1, 1, 1, 60, 1320)

    def test_invalid_center_ra_high(self):
        with pytest.raises(ValueError, match="center_ra"):
            create_mosaic_plan("X", 24, 0, 1, 1, 1, 1, 60, 1320)

    def test_invalid_center_dec_low(self):
        with pytest.raises(ValueError, match="center_dec"):
            create_mosaic_plan("X", 12, -91, 1, 1, 1, 1, 60, 1320)

    def test_invalid_center_dec_high(self):
        with pytest.raises(ValueError, match="center_dec"):
            create_mosaic_plan("X", 12, 91, 1, 1, 1, 1, 60, 1320)

    def test_invalid_delta_ra(self):
        with pytest.raises(ValueError, match="delta_ra"):
            create_mosaic_plan("X", 12, 0, 1, 1, 0, 1, 60, 1320)

    def test_invalid_delta_dec(self):
        with pytest.raises(ValueError, match="delta_dec"):
            create_mosaic_plan("X", 12, 0, 1, 1, 1, -1, 60, 1320)

    def test_pole_dec_90(self):
        with pytest.raises(ValueError, match="±90"):
            create_mosaic_plan("X", 12, 90, 1, 1, 1, 1, 60, 1320)

    def test_pole_dec_minus_90(self):
        with pytest.raises(ValueError, match="±90"):
            create_mosaic_plan("X", 12, -90, 1, 1, 1, 1, 60, 1320)

    def test_near_pole_warns(self):
        with pytest.warns(match="near a pole"):
            create_mosaic_plan("X", 12, 86, 1, 1, 1, 1, 60, 1320)

    def test_negative_width(self):
        with pytest.raises(ValueError, match="width"):
            create_mosaic_plan("X", 12, 0, -1, 1, 1, 1, 60, 1320)

    def test_negative_height(self):
        with pytest.raises(ValueError, match="height"):
            create_mosaic_plan("X", 12, 0, 1, -1, 1, 1, 60, 1320)
