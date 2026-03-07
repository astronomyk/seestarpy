"""Unit tests for create_polygon_plan() and its helpers in plan.py."""

import math

import pytest

from seestarpy.plan import (
    _gnomonic_forward,
    _gnomonic_inverse,
    _point_in_polygon,
    _spherical_centroid,
    create_polygon_plan,
    create_quadrilateral_plan,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestSphericalCentroid:
    def test_equator_square(self):
        """Centroid of 4 corners symmetric around (12h, 0°) should be ~(12h, 0°)."""
        corners = [(11.9, -1.0), (12.1, -1.0), (12.1, 1.0), (11.9, 1.0)]
        ra0, dec0 = _spherical_centroid(corners)
        assert math.degrees(ra0) / 15.0 == pytest.approx(12.0, abs=0.01)
        assert math.degrees(dec0) == pytest.approx(0.0, abs=0.01)

    def test_wraparound(self):
        """Centroid of corners straddling 0h/24h should be near 0h, not 12h."""
        corners = [(23.9, 0.0), (0.1, 0.0), (0.1, 1.0), (23.9, 1.0)]
        ra0, dec0 = _spherical_centroid(corners)
        ra_h = math.degrees(ra0) / 15.0
        # Should be near 0h (i.e. either <0.2 or >23.8)
        assert ra_h < 0.2 or ra_h > 23.8


class TestGnomonicRoundtrip:
    def test_roundtrip(self):
        """Forward then inverse gnomonic should return the original point."""
        ra0 = math.radians(180.0)
        dec0 = math.radians(45.0)
        ra_in = math.radians(181.0)
        dec_in = math.radians(46.0)
        xi, eta = _gnomonic_forward(ra_in, dec_in, ra0, dec0)
        ra_out, dec_out = _gnomonic_inverse(xi, eta, ra0, dec0)
        assert math.degrees(ra_out) == pytest.approx(181.0, abs=1e-6)
        assert math.degrees(dec_out) == pytest.approx(46.0, abs=1e-6)

    def test_centre_maps_to_origin(self):
        """The tangent point itself should project to (0, 0)."""
        ra0 = math.radians(90.0)
        dec0 = math.radians(30.0)
        xi, eta = _gnomonic_forward(ra0, dec0, ra0, dec0)
        assert xi == pytest.approx(0.0, abs=1e-12)
        assert eta == pytest.approx(0.0, abs=1e-12)


class TestPointInPolygon:
    def test_inside_square(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert _point_in_polygon(0.5, 0.5, square) is True

    def test_outside_square(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert _point_in_polygon(2.0, 0.5, square) is False

    def test_concave_quad(self):
        """Concave quad (chevron): test inside and outside points."""
        # Chevron shape: concave at (1, 0.5), opens rightward
        chevron = [(0, 0), (2, 0), (1, 0.5), (2, 1)]
        # (0.5, 0.2) is inside the lower-left region
        assert _point_in_polygon(0.5, 0.2, chevron) is True
        # (3.0, 0.5) is clearly outside
        assert _point_in_polygon(3.0, 0.5, chevron) is False


# ---------------------------------------------------------------------------
# create_quadrilateral_plan — basic functionality
# ---------------------------------------------------------------------------

class TestQuadPlanRectangle:
    """Test with a rectangle at dec=0 (simplest case)."""

    def test_panel_count(self):
        """A 2° x 2° rectangle with 1° spacing should produce ~4 panels."""
        result = create_polygon_plan(
            plan_name="Rect",
            corners=[
                (12.0 - 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, 1.0),
                (12.0 - 1.0 / 15, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        # Should have at least 2 panels and the structure should be valid
        assert len(result["list"]) >= 2

    def test_plan_dict_schema(self):
        """Output should have the same schema as create_mosaic_plan."""
        result = create_polygon_plan(
            plan_name="Schema",
            corners=[
                (12.0 - 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, 1.0),
                (12.0 - 1.0 / 15, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        assert "plan_name" in result
        assert "update_time_seestar" in result
        assert "list" in result
        assert result["plan_name"] == "Schema"

        target = result["list"][0]
        required_keys = {
            "target_id", "target_name", "alias_name",
            "target_ra_dec", "lp_filter", "start_min", "duration_min",
        }
        assert required_keys.issubset(target.keys())
        assert isinstance(target["target_ra_dec"], list)
        assert len(target["target_ra_dec"]) == 2

    def test_all_ra_in_range(self):
        result = create_polygon_plan(
            plan_name="Range",
            corners=[
                (12.0 - 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, 1.0),
                (12.0 - 1.0 / 15, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        for panel in result["list"]:
            ra = panel["target_ra_dec"][0]
            assert 0 <= ra < 24, f"RA {ra} out of [0, 24)"

    def test_sequential_scheduling(self):
        result = create_polygon_plan(
            plan_name="Seq",
            corners=[
                (12.0 - 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, -1.0),
                (12.0 + 1.0 / 15, 1.0),
                (12.0 - 1.0 / 15, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        panels = result["list"]
        for i in range(1, len(panels)):
            prev_end = panels[i - 1]["start_min"] + panels[i - 1]["duration_min"]
            assert panels[i]["start_min"] == prev_end


class TestQuadPlanWraparound:
    """Corners straddling 0h/24h should work correctly."""

    def test_ra_wraparound(self):
        result = create_polygon_plan(
            plan_name="Wrap",
            corners=[
                (23.9, -1.0),
                (0.1, -1.0),
                (0.1, 1.0),
                (23.9, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=120,
            start_min=1320,
        )
        assert len(result["list"]) >= 1
        for panel in result["list"]:
            ra = panel["target_ra_dec"][0]
            assert 0 <= ra < 24, f"RA {ra} out of [0, 24)"


class TestQuadPlanSingleTile:
    """When spacing > quadrilateral extent, should get 1 tile."""

    def test_large_spacing(self):
        result = create_polygon_plan(
            plan_name="Single",
            corners=[
                (12.0, 0.0),
                (12.01, 0.0),
                (12.01, 0.1),
                (12.0, 0.1),
            ],
            delta_ra=5.0,
            delta_dec=5.0,
            t_total=60,
            start_min=1320,
        )
        assert len(result["list"]) == 1
        assert result["list"][0]["duration_min"] == 60


class TestQuadPlanLpFilter:
    def test_lp_filter_propagated(self):
        result = create_polygon_plan(
            plan_name="LP",
            corners=[
                (12.0, 0.0), (12.1, 0.0), (12.1, 1.0), (12.0, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
            lp_filter=True,
        )
        for panel in result["list"]:
            assert panel["lp_filter"] is True


class TestQuadPlanNaming:
    def test_default_prefix(self):
        result = create_polygon_plan(
            plan_name="Name",
            corners=[
                (12.0, 0.0), (12.1, 0.0), (12.1, 1.0), (12.0, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
        )
        assert result["list"][0]["target_name"].startswith("Poly_")

    def test_custom_prefix(self):
        result = create_polygon_plan(
            plan_name="Name",
            corners=[
                (12.0, 0.0), (12.1, 0.0), (12.1, 1.0), (12.0, 1.0),
            ],
            delta_ra=1.0,
            delta_dec=1.0,
            t_total=60,
            start_min=1320,
            target_name_prefix="Veil",
        )
        assert result["list"][0]["target_name"].startswith("Veil_")


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestQuadPlanValidation:
    def test_too_few_corners(self):
        with pytest.raises(ValueError, match="at least 3"):
            create_polygon_plan(
                "X", [(12, 0), (12.1, 0)],
                1.0, 1.0, 60, 1320,
            )

    def test_invalid_ra(self):
        with pytest.raises(ValueError, match="RA"):
            create_polygon_plan(
                "X", [(25, 0), (12.1, 0), (12.1, 1), (12, 1)],
                1.0, 1.0, 60, 1320,
            )

    def test_invalid_dec(self):
        with pytest.raises(ValueError, match="Dec"):
            create_polygon_plan(
                "X", [(12, -91), (12.1, 0), (12.1, 1), (12, 1)],
                1.0, 1.0, 60, 1320,
            )

    def test_invalid_delta_ra(self):
        with pytest.raises(ValueError, match="delta_ra"):
            create_polygon_plan(
                "X", [(12, 0), (12.1, 0), (12.1, 1), (12, 1)],
                0, 1.0, 60, 1320,
            )

    def test_invalid_delta_dec(self):
        with pytest.raises(ValueError, match="delta_dec"):
            create_polygon_plan(
                "X", [(12, 0), (12.1, 0), (12.1, 1), (12, 1)],
                1.0, -1.0, 60, 1320,
            )

    def test_degenerate_quad(self):
        """Four identical points should raise ValueError."""
        with pytest.raises(ValueError, match="[Dd]egenerate"):
            create_polygon_plan(
                "X", [(12, 0), (12, 0), (12, 0), (12, 0)],
                1.0, 1.0, 60, 1320,
            )

    def test_near_pole_warns(self):
        with pytest.warns(match="near a pole"):
            create_polygon_plan(
                "X",
                [(12, 86), (12.1, 86), (12.1, 87), (12, 87)],
                1.0, 1.0, 60, 1320,
            )


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------

class TestAlias:
    def test_create_quadrilateral_plan_is_alias(self):
        assert create_quadrilateral_plan is create_polygon_plan


# ---------------------------------------------------------------------------
# Polygons with more than 4 sides
# ---------------------------------------------------------------------------

class TestTriangle:
    def test_triangle_produces_panels(self):
        result = create_polygon_plan(
            plan_name="Tri",
            corners=[
                (12.0, 0.0),
                (12.2, 0.0),
                (12.1, 1.0),
            ],
            delta_ra=0.5,
            delta_dec=0.5,
            t_total=60,
            start_min=1320,
        )
        assert len(result["list"]) >= 1
        for panel in result["list"]:
            ra = panel["target_ra_dec"][0]
            assert 0 <= ra < 24


class TestPentagon:
    def test_pentagon_produces_panels(self):
        result = create_polygon_plan(
            plan_name="Penta",
            corners=[
                (12.0, 0.0),
                (12.1, -0.5),
                (12.2, 0.0),
                (12.15, 0.5),
                (12.05, 0.5),
            ],
            delta_ra=0.3,
            delta_dec=0.3,
            t_total=90,
            start_min=1320,
        )
        assert len(result["list"]) >= 1
        assert result["plan_name"] == "Penta"

    def test_pentagon_schema(self):
        result = create_polygon_plan(
            plan_name="PentaSchema",
            corners=[
                (12.0, 0.0),
                (12.1, -0.5),
                (12.2, 0.0),
                (12.15, 0.5),
                (12.05, 0.5),
            ],
            delta_ra=0.3,
            delta_dec=0.3,
            t_total=90,
            start_min=1320,
        )
        target = result["list"][0]
        required_keys = {
            "target_id", "target_name", "alias_name",
            "target_ra_dec", "lp_filter", "start_min", "duration_min",
        }
        assert required_keys.issubset(target.keys())
