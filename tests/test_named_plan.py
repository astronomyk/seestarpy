"""Unit tests for resolve_name() and create_named_plan() in plan.py."""

from unittest.mock import patch, Mock

import pytest

from seestarpy.plan import (
    _parse_hhmm,
    create_named_plan,
    resolve_name,
)

# ---------------------------------------------------------------------------
# Sample Sesame XML responses
# ---------------------------------------------------------------------------

_SESAME_M42 = """\
<?xml version="1.0" ?>
<Sesame>
  <Target>
    <name>M42</name>
    <Resolver name="S=Simbad">
      <jradeg>83.8221</jradeg>
      <jdedeg>-5.3911</jdedeg>
    </Resolver>
  </Target>
</Sesame>
"""

_SESAME_M31 = """\
<?xml version="1.0" ?>
<Sesame>
  <Target>
    <name>M31</name>
    <Resolver name="S=Simbad">
      <jradeg>10.6847</jradeg>
      <jdedeg>41.2688</jdedeg>
    </Resolver>
  </Target>
</Sesame>
"""

_SESAME_NOT_FOUND = """\
<?xml version="1.0" ?>
<Sesame>
  <Target>
    <name>XYZNOTREAL</name>
  </Target>
</Sesame>
"""


def _mock_sesame_response(xml_text, status=200):
    resp = Mock()
    resp.text = xml_text
    resp.status_code = status
    resp.raise_for_status = Mock()
    return resp


def _sesame_side_effect(url, **kwargs):
    """Return different XML depending on the queried name."""
    if "M42" in url:
        return _mock_sesame_response(_SESAME_M42)
    if "M31" in url:
        return _mock_sesame_response(_SESAME_M31)
    if "NGC%20884" in url or "NGC+884" in url or "NGC 884" in url:
        # Reuse M31 coords for simplicity
        return _mock_sesame_response(_SESAME_M31)
    if "XYZNOTREAL" in url:
        return _mock_sesame_response(_SESAME_NOT_FOUND)
    return _mock_sesame_response(_SESAME_NOT_FOUND)


# ---------------------------------------------------------------------------
# _parse_hhmm
# ---------------------------------------------------------------------------

class TestParseHhmm:
    def test_normal(self):
        assert _parse_hhmm("22:30") == 1350

    def test_midnight(self):
        assert _parse_hhmm("00:00") == 0

    def test_just_before_midnight(self):
        assert _parse_hhmm("23:59") == 1439

    def test_with_spaces(self):
        assert _parse_hhmm("  01:15  ") == 75

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="hh:mm"):
            _parse_hhmm("2230")

    def test_invalid_hour(self):
        with pytest.raises(ValueError, match="Invalid"):
            _parse_hhmm("25:00")

    def test_invalid_minute(self):
        with pytest.raises(ValueError, match="Invalid"):
            _parse_hhmm("12:61")


# ---------------------------------------------------------------------------
# resolve_name
# ---------------------------------------------------------------------------

class TestResolveName:
    @patch("seestarpy.plan._requests.get")
    def test_m42(self, mock_get):
        mock_get.return_value = _mock_sesame_response(_SESAME_M42)
        ra, dec = resolve_name("M42")
        assert ra == pytest.approx(83.8221 / 15.0, abs=1e-4)
        assert dec == pytest.approx(-5.3911, abs=1e-4)

    @patch("seestarpy.plan._requests.get")
    def test_not_found_raises(self, mock_get):
        mock_get.return_value = _mock_sesame_response(_SESAME_NOT_FOUND)
        with pytest.raises(LookupError, match="not found"):
            resolve_name("XYZNOTREAL")

    @patch("seestarpy.plan._requests.get")
    def test_connection_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.ConnectionError("timeout")
        with pytest.raises(ConnectionError, match="Sesame"):
            resolve_name("M42")


# ---------------------------------------------------------------------------
# create_named_plan
# ---------------------------------------------------------------------------

class TestCreateNamedPlan:
    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_basic_two_targets(self, mock_get):
        result = create_named_plan(
            plan_name="Evening",
            targets=[
                ("M42", "21:00"),
                ("M31", "22:30"),
            ],
            end_time="23:45",
        )
        assert result["plan_name"] == "Evening"
        assert len(result["list"]) == 2

        t0 = result["list"][0]
        assert t0["target_name"] == "M42"
        assert t0["start_min"] == 21 * 60  # 1260
        assert t0["duration_min"] == 90  # 22:30 - 21:00

        t1 = result["list"][1]
        assert t1["target_name"] == "M31"
        assert t1["start_min"] == 22 * 60 + 30  # 1350
        assert t1["duration_min"] == 75  # 23:45 - 22:30

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_midnight_wraparound(self, mock_get):
        """Times after midnight should automatically wrap."""
        result = create_named_plan(
            plan_name="Late Night",
            targets=[
                ("M42", "23:00"),
                ("M31", "01:30"),
            ],
            end_time="03:00",
        )
        panels = result["list"]
        assert panels[0]["start_min"] == 23 * 60  # 1380
        assert panels[1]["start_min"] == 1440 + 90  # 1530 (01:30 next day)
        assert panels[0]["duration_min"] == 150  # 1530 - 1380
        assert panels[1]["duration_min"] == 90   # 1620 - 1530

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_lp_filter_default(self, mock_get):
        result = create_named_plan(
            plan_name="LP",
            targets=[("M42", "21:00")],
            end_time="22:00",
            lp_filter=True,
        )
        assert result["list"][0]["lp_filter"] is True

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_lp_filter_per_target(self, mock_get):
        result = create_named_plan(
            plan_name="LP",
            targets=[
                ("M42", "21:00", True),
                ("M31", "22:00", False),
            ],
            end_time="23:00",
        )
        assert result["list"][0]["lp_filter"] is True
        assert result["list"][1]["lp_filter"] is False

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_plan_dict_schema(self, mock_get):
        result = create_named_plan(
            plan_name="Schema",
            targets=[("M42", "21:00")],
            end_time="22:00",
        )
        assert "plan_name" in result
        assert "update_time_seestar" in result
        assert "list" in result
        target = result["list"][0]
        required_keys = {
            "target_id", "target_name", "alias_name",
            "target_ra_dec", "lp_filter", "start_min", "duration_min",
        }
        assert required_keys.issubset(target.keys())
        assert isinstance(target["target_ra_dec"], list)
        assert len(target["target_ra_dec"]) == 2

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_unique_target_ids(self, mock_get):
        result = create_named_plan(
            plan_name="IDs",
            targets=[
                ("M42", "21:00"),
                ("M31", "22:00"),
            ],
            end_time="23:00",
        )
        ids = [t["target_id"] for t in result["list"]]
        assert len(ids) == len(set(ids))

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_duplicate_name_resolved_once(self, mock_get):
        """Same target appearing twice should only query Sesame once."""
        create_named_plan(
            plan_name="Dup",
            targets=[
                ("M42", "21:00"),
                ("M42", "22:00"),
            ],
            end_time="23:00",
        )
        # M42 appears twice but should only be resolved once
        m42_calls = [c for c in mock_get.call_args_list if "M42" in c[0][0]]
        assert len(m42_calls) == 1

    def test_empty_targets_raises(self):
        with pytest.raises(ValueError, match="empty"):
            create_named_plan("X", [], "22:00")

    def test_bad_tuple_length_raises(self):
        with pytest.raises(ValueError, match="elements"):
            create_named_plan("X", [("M42",)], "22:00")

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_ra_in_range(self, mock_get):
        result = create_named_plan(
            plan_name="Range",
            targets=[("M42", "21:00")],
            end_time="22:00",
        )
        ra = result["list"][0]["target_ra_dec"][0]
        assert 0 <= ra < 24


# ---------------------------------------------------------------------------
# Explicit RA/Dec coordinates
# ---------------------------------------------------------------------------

class TestCreateNamedPlanCoords:
    def test_explicit_coords_no_network(self):
        """RA/Dec tuples should not trigger any Sesame calls."""
        # No mock — if it tried to call requests.get it would fail
        result = create_named_plan(
            plan_name="Coords",
            targets=[
                ((5.588, -5.39), "21:00"),
                ((0.712, 41.27), "22:30"),
            ],
            end_time="23:30",
        )
        assert len(result["list"]) == 2
        t0 = result["list"][0]
        assert t0["target_ra_dec"] == [5.588, -5.39]
        assert t0["duration_min"] == 90

        t1 = result["list"][1]
        assert t1["target_ra_dec"] == [0.712, 41.27]
        assert t1["duration_min"] == 60

    def test_explicit_coords_auto_label(self):
        """RA/Dec targets should get an auto-generated label."""
        result = create_named_plan(
            plan_name="Label",
            targets=[([5.588, -5.39], "21:00")],
            end_time="22:00",
        )
        name = result["list"][0]["target_name"]
        assert "5.588" in name
        assert "-5.39" in name

    @patch("seestarpy.plan._requests.get", side_effect=_sesame_side_effect)
    def test_mixed_names_and_coords(self, mock_get):
        """Mix of name strings and RA/Dec pairs in the same plan."""
        result = create_named_plan(
            plan_name="Mixed",
            targets=[
                ("M42", "21:00"),
                ((0.712, 41.27), "22:00"),
                ("M31", "23:00"),
            ],
            end_time="00:30",
        )
        assert len(result["list"]) == 3
        assert result["list"][0]["target_name"] == "M42"
        assert result["list"][1]["target_ra_dec"] == [0.712, 41.27]
        assert result["list"][2]["target_name"] == "M31"

    def test_coords_with_lp_filter(self):
        result = create_named_plan(
            plan_name="LP",
            targets=[
                ((5.588, -5.39), "21:00", True),
            ],
            end_time="22:00",
        )
        assert result["list"][0]["lp_filter"] is True

    def test_coords_list_format(self):
        """RA/Dec as a list [ra, dec] should also work."""
        result = create_named_plan(
            plan_name="List",
            targets=[([12.0, 45.0], "21:00")],
            end_time="22:00",
        )
        assert result["list"][0]["target_ra_dec"] == [12.0, 45.0]
