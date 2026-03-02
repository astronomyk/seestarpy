"""Unit tests for plot_mosaic_plan() in plan.py."""

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from seestarpy.plan import create_mosaic_plan, plot_mosaic_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_3x3(center_ra=12.0, center_dec=0.0):
    """Create a 3x3 mosaic plan for testing."""
    return create_mosaic_plan(
        plan_name="Test 3x3",
        center_ra=center_ra,
        center_dec=center_dec,
        width=3.0,
        height=3.0,
        delta_ra=1.0,
        delta_dec=1.0,
        t_total=180,
        start_min=1320,
    )


def _panel_lines(ax):
    """Return lines that are panel outlines (linewidth > 0.5)."""
    return [ln for ln in ax.lines if ln.get_linewidth() > 0.5]


def _grid_lines(ax):
    """Return lines that are grid lines (linewidth <= 0.5)."""
    return [ln for ln in ax.lines if ln.get_linewidth() <= 0.5]


# ---------------------------------------------------------------------------
# 3x3 grid near Dec=0
# ---------------------------------------------------------------------------

class TestPlotMosaicDec0:
    def test_returns_axes(self):
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan)
        assert isinstance(ax, matplotlib.axes.Axes)
        plt.close("all")

    def test_nine_panel_outlines(self):
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan)
        assert len(_panel_lines(ax)) == 9
        plt.close("all")

    def test_grid_lines_present(self):
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan)
        assert len(_grid_lines(ax)) > 0
        plt.close("all")

    def test_nine_text_labels(self):
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan)
        assert len(ax.texts) == 9
        plt.close("all")

    def test_title_set(self):
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan)
        assert ax.get_title() == "Test 3x3"
        plt.close("all")

    def test_view_is_zoomed(self):
        """Axes limits should be much smaller than the full Mollweide range."""
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan)
        x_range = ax.get_xlim()[1] - ax.get_xlim()[0]
        y_range = ax.get_ylim()[1] - ax.get_ylim()[0]
        # Full Mollweide x spans ~5.66, y spans ~2.83; zoomed should be tiny
        assert x_range < 1.0
        assert y_range < 1.0
        plt.close("all")


# ---------------------------------------------------------------------------
# 3x3 grid near Dec=88 — cos(dec) stress test
# ---------------------------------------------------------------------------

class TestPlotMosaicDec88:
    def test_runs_without_error(self):
        with pytest.warns(match="near a pole"):
            plan = _make_3x3(center_dec=88.0)
        ax = plot_mosaic_plan(plan)
        assert isinstance(ax, matplotlib.axes.Axes)
        plt.close("all")

    def test_nine_panels_and_labels(self):
        with pytest.warns(match="near a pole"):
            plan = _make_3x3(center_dec=88.0)
        ax = plot_mosaic_plan(plan)
        assert len(_panel_lines(ax)) == 9
        assert len(ax.texts) == 9
        plt.close("all")

    def test_ra_spread_wider_than_equator(self):
        """At Dec=88, panels should span a much wider RA range than at Dec=0."""
        eq_plan = _make_3x3(center_dec=0.0)
        with pytest.warns(match="near a pole"):
            pole_plan = _make_3x3(center_dec=88.0)

        eq_ras = [t["target_ra_dec"][0] for t in eq_plan["list"]]
        pole_ras = [t["target_ra_dec"][0] for t in pole_plan["list"]]

        eq_spread = max(eq_ras) - min(eq_ras)
        pole_spread = max(pole_ras) - min(pole_ras)

        assert pole_spread > eq_spread * 5
        plt.close("all")


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------

class TestCustomAx:
    def test_uses_provided_axes(self):
        fig, ax = plt.subplots()
        plan = _make_3x3()
        returned_ax = plot_mosaic_plan(plan, ax=ax)
        assert returned_ax is ax
        plt.close("all")


class TestCustomFov:
    def test_non_default_fov(self):
        plan = _make_3x3()
        ax = plot_mosaic_plan(plan, fov_width=1.5, fov_height=2.0)
        assert len(_panel_lines(ax)) == 9
        plt.close("all")
