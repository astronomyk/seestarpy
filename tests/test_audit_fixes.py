"""Regression tests for the defects found in the v0.7.0 src/ audit.

Each test here pins behaviour that was wrong in a way no existing test
caught, and three of the four were documented as working:

- ``ui.filter_wheel`` rejected ``"lp"`` / ``"ircut"``, the two names the
  docs lead with, because the guard list held only two of the four keys the
  mapping supported.
- ``ui.goto`` returned ``None`` for an unrecognised string instead of
  raising: the ``else: raise`` was unreachable for every ``str``, so a
  typo'd target was a silent no-op that looked like success.
- ``status.get_target_name`` read ``group_name`` off the JSON-RPC envelope
  instead of out of ``result``, so it always returned ``None``.
- ``status.status_bar(return_type=...)`` never read the parameter, so
  ``"dict"`` returned the formatted string.
- ``connection.keepalive`` silently did nothing useful when
  ``PERSIST_CONNECTIONS`` was False, which would abort a polar alignment
  ~15 s in exactly as it did before keepalive existed.
"""

from unittest.mock import patch

import pytest

from seestarpy import connection, status, ui


# ---------------------------------------------------------------------------
# ui.filter_wheel — the guard list must match the name mapping
# ---------------------------------------------------------------------------

class TestFilterWheelNames:
    @pytest.mark.parametrize("name, expected_pos", [
        ("open", 1), ("ircut", 1), ("narrow", 2), ("lp", 2),
        ("OPEN", 1), ("IRCUT", 1), ("Narrow", 2), ("LP", 2),
    ])
    def test_every_mapped_name_is_accepted(self, name, expected_pos):
        with patch("seestarpy.raw.set_wheel_position") as mock_set:
            ui.filter_wheel(name)
        mock_set.assert_called_once_with(expected_pos)

    @pytest.mark.parametrize("pos, expected", [(1, 1), (2, 2)])
    def test_integer_positions_still_work(self, pos, expected):
        with patch("seestarpy.raw.set_wheel_position") as mock_set:
            ui.filter_wheel(pos)
        mock_set.assert_called_once_with(expected)

    @pytest.mark.parametrize("bad", ["dark", "", "3", "nonsense"])
    def test_unknown_name_raises_and_sends_nothing(self, bad):
        with patch("seestarpy.raw.set_wheel_position") as mock_set:
            with pytest.raises(ValueError):
                ui.filter_wheel(bad)
        mock_set.assert_not_called()

    @pytest.mark.parametrize("bad", [0, 3, -1])
    def test_out_of_range_integer_raises(self, bad):
        with patch("seestarpy.raw.set_wheel_position") as mock_set:
            with pytest.raises(ValueError):
                ui.filter_wheel(bad)
        mock_set.assert_not_called()

    def test_no_argument_reads_the_current_position(self):
        with patch("seestarpy.ui.get_filter", return_value=1) as mock_get:
            assert ui.filter_wheel() == 1
        mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# ui.goto — an unrecognised string must raise, not return None
# ---------------------------------------------------------------------------

class TestGotoValidation:
    @pytest.mark.parametrize("bad", ["m42", "", "M 81", "parked", "horizontal"])
    def test_unrecognised_string_raises(self, bad):
        with patch("seestarpy.raw.scope_goto") as goto, \
             patch("seestarpy.raw.scope_park") as park, \
             patch("seestarpy.raw.scope_move_to_horizon") as horizon:
            with pytest.raises(ValueError):
                ui.goto(bad)
        # A typo must not be mistaken for one of the shortcuts.
        goto.assert_not_called()
        park.assert_not_called()
        horizon.assert_not_called()

    # ui.goto now blocks until the mount reports the move finished, so these
    # dispatch tests pass timeout=0: the RPC still goes out, but with no
    # event source behind the mock there is nothing to wait for.
    def test_park_shortcut(self):
        with patch("seestarpy.raw.scope_park") as park:
            ui.goto("park", timeout=0, verbose=False)
        park.assert_called_once()

    def test_horizon_shortcut(self):
        with patch("seestarpy.raw.scope_move_to_horizon") as horizon:
            ui.goto("HORIZON", timeout=0, verbose=False)
        horizon.assert_called_once()

    def test_coordinate_pair(self):
        with patch("seestarpy.raw.scope_goto") as goto:
            ui.goto((13.4, 54.8), timeout=0, verbose=False)
        goto.assert_called_once_with(13.4, 54.8)

    @pytest.mark.parametrize("bad", [(), (1,), (1, 2, 3), 42, None])
    def test_bad_shapes_raise(self, bad):
        with patch("seestarpy.raw.scope_goto"):
            with pytest.raises(ValueError):
                ui.goto(bad)


# ---------------------------------------------------------------------------
# status.get_target_name — read the value out of ``result``
# ---------------------------------------------------------------------------

class TestGetTargetName:
    # Patches raw, not connection.send_command: status now routes every query
    # through the raw wrappers rather than building payloads itself.
    def test_reads_group_name_from_result(self):
        reply = {
            "jsonrpc": "2.0",
            "method": "get_sequence_setting",
            "result": {"group_name": "M 81", "park_mount": False},
            "code": 0,
            "id": 1,
        }
        with patch("seestarpy.raw.get_sequence_setting", return_value=reply):
            assert status.get_target_name() == "M 81"

    def test_missing_result_gives_none_not_a_crash(self):
        err = {"jsonrpc": "2.0", "error": "method not found", "code": 103}
        with patch("seestarpy.raw.get_sequence_setting", return_value=err):
            assert status.get_target_name() is None

    def test_null_result_gives_none(self):
        with patch("seestarpy.raw.get_sequence_setting",
                   return_value={"result": None, "code": 0}):
            assert status.get_target_name() is None


# ---------------------------------------------------------------------------
# status.status_bar — return_type must actually be honoured
# ---------------------------------------------------------------------------

_DEVICE = {
    "result": {
        "device": {"firmware_ver_string": "8.46", "focal_len": 250.0},
        "mount": {"tracking": True, "equ_mode": True, "close": False},
        "pi_status": {"battery_capacity": 62},
        "storage": {"storage_volume": [{"free_mb": 28050}]},
        "setting": {"stack_dither": {"enable": True, "pix": 60, "interval": 5}},
        "balance_sensor": {"data": {"angle": 1.234}},
    }
}
_APP = {
    "result": {
        "View": {
            "mode": "star", "state": "working", "stage": "Stack",
            "target_name": "NGC 869", "target_ra_dec": [2.32, 57.13],
            "lp_filter": False, "gain": 80,
            "Stack": {"stacked_frame": 204, "dropped_frame": 6,
                      "Exposure": {"exp_ms": 10000}},
        }
    }
}
_EQU = {"result": {"ra": 2.32, "dec": 57.13}, "code": 0}
_HORIZ = {"result": [42.3, 312.7], "code": 0}


def _patched_status_bar(**kwargs):
    with patch("seestarpy.raw.get_device_state", return_value=_DEVICE), \
         patch("seestarpy.raw.iscope_get_app_state", return_value=_APP), \
         patch("seestarpy.raw.scope_get_equ_coord", return_value=_EQU), \
         patch("seestarpy.raw.scope_get_horiz_coord", return_value=_HORIZ):
        return status.status_bar(**kwargs)


class TestStatusBarReturnType:
    def test_default_is_a_string(self):
        assert isinstance(_patched_status_bar(), str)

    def test_str_is_a_string(self):
        assert isinstance(_patched_status_bar(return_type="str"), str)

    def test_dict_returns_a_dict(self):
        out = _patched_status_bar(return_type="dict")
        assert isinstance(out, dict)

    def test_dict_carries_the_live_values_unformatted(self):
        out = _patched_status_bar(return_type="dict")
        assert out["mode"] == "star"
        assert out["state"] == "working"
        assert out["target_name"] == "NGC 869"
        assert out["stacked_frames"] == 204
        assert out["dropped_frames"] == 6
        assert out["gain"] == 80
        assert out["battery_percent"] == 62
        assert out["free_mb"] == 28050
        assert out["firmware"] == "8.46"
        assert out["tracking"] is True
        assert out["equ_mode"] is True
        assert out["exp_ms"] == 10000
        assert out["ra"] == pytest.approx(2.32)
        assert out["dec"] == pytest.approx(57.13)
        assert out["alt"] == pytest.approx(42.3)
        assert out["az"] == pytest.approx(312.7)
        assert out["compass"] == "NW"
        assert out["dither_enabled"] is True
        assert out["dither_arcmin"] == pytest.approx(2.39, abs=0.01)

    def test_missing_fields_are_none_not_dashes(self):
        """The table's ``---`` placeholder must not leak into the dict."""
        err = {"jsonrpc": "2.0", "error": "method not found", "code": 103}
        with patch("seestarpy.raw.get_device_state", return_value=err), \
             patch("seestarpy.raw.iscope_get_app_state", return_value=err), \
             patch("seestarpy.raw.scope_get_equ_coord", return_value=err), \
             patch("seestarpy.raw.scope_get_horiz_coord", return_value=err):
            out = status.status_bar(return_type="dict")
        assert out["mode"] is None
        assert out["gain"] is None
        assert out["ra"] is None
        assert out["compass"] is None
        assert not any(v == "---" for v in out.values())

    def test_table_is_rendered_from_the_same_values(self):
        """Both return types must agree, so the dict can be trusted."""
        table = _patched_status_bar()
        values = _patched_status_bar(return_type="dict")
        assert values["target_name"] in table
        assert str(values["stacked_frames"]) in table
        assert values["firmware"] in table

    @pytest.mark.parametrize("bad", ["json", "list", "", None, "DICT"])
    def test_unknown_return_type_raises(self, bad):
        with pytest.raises(ValueError):
            _patched_status_bar(return_type=bad)


# ---------------------------------------------------------------------------
# connection.keepalive — refuse to run without a persistent connection
# ---------------------------------------------------------------------------

class TestKeepaliveRequiresPersistentConnection:
    def test_raises_when_pooling_is_disabled(self):
        original = connection.PERSIST_CONNECTIONS
        connection.PERSIST_CONNECTIONS = False
        try:
            with pytest.raises(RuntimeError, match="PERSIST_CONNECTIONS"):
                with connection.keepalive(ip="10.0.0.1"):
                    pass                      # pragma: no cover
        finally:
            connection.PERSIST_CONNECTIONS = original

    def test_does_not_open_a_connection_when_it_refuses(self):
        original = connection.PERSIST_CONNECTIONS
        connection.PERSIST_CONNECTIONS = False
        try:
            with patch("seestarpy.connection._get_connection") as get_conn:
                with pytest.raises(RuntimeError):
                    with connection.keepalive(ip="10.0.0.1"):
                        pass                  # pragma: no cover
            get_conn.assert_not_called()
        finally:
            connection.PERSIST_CONNECTIONS = original

    def test_starts_and_stops_the_ping_when_pooling_is_on(self):
        assert connection.PERSIST_CONNECTIONS is True
        with patch("seestarpy.connection._get_connection") as get_conn:
            conn = get_conn.return_value
            with connection.keepalive(ip="10.0.0.1") as held:
                assert held is conn
                conn.start_keepalive.assert_called_once()
                conn.stop_keepalive.assert_not_called()
            conn.stop_keepalive.assert_called_once()

    def test_event_handler_is_removed_on_exit(self):
        def on_event(_):
            pass                              # pragma: no cover

        with patch("seestarpy.connection._get_connection") as get_conn:
            conn = get_conn.return_value
            with connection.keepalive(ip="10.0.0.1", on_event=on_event):
                conn.add_event_handler.assert_called_once_with(on_event)
            conn.remove_event_handler.assert_called_once_with(on_event)


# ---------------------------------------------------------------------------
# events.event_listener — target resolved per attempt, not at import
# ---------------------------------------------------------------------------

class TestListenerResolvesTargetLate:
    def test_listener_holds_no_snapshot_of_default_ip(self):
        """A snapshot here made start_listener() connect to the old scope."""
        from seestarpy.events import event_listener as el

        assert not hasattr(el, "DEFAULT_IP")
        assert el.connection is connection


# ---------------------------------------------------------------------------
# status.py must go through raw, not build its own payloads
# ---------------------------------------------------------------------------

class TestStatusRoutesThroughRaw:
    """The two functions that hand-rolled payloads were the two that were
    broken; the envelope handling worth reusing lives in ``raw``."""

    def test_get_exposure_uses_raw(self):
        reply = {"result": {"exp_ms": {"stack_l": 20000, "continuous": 500}}}
        with patch("seestarpy.raw.get_setting", return_value=reply) as mock:
            assert status.get_exposure() == 20000
            assert status.get_exposure("continuous") == 500
        assert mock.call_count == 2

    def test_get_filter_uses_raw(self):
        reply = {"result": 1, "code": 0}
        with patch("seestarpy.raw.get_wheel_position", return_value=reply) as mock:
            assert status.get_filter()["result"] == 1
        mock.assert_called_once()

    def test_status_module_no_longer_imports_send_command(self):
        assert not hasattr(status, "send_command")


# ---------------------------------------------------------------------------
# Shared helpers: one implementation, imported rather than copied
# ---------------------------------------------------------------------------

class TestSharedNumericHelpers:
    @pytest.mark.parametrize("value, expected", [
        (42, 42), (1.5, 1.5), (0, 0), (-3, -3),
        ("---", None), ("", None), (None, None), ({}, None), ([], None),
        (True, None), (False, None),          # a flag is not a measurement
    ])
    def test_as_number(self, value, expected):
        assert status.as_number(value) == expected

    @pytest.mark.parametrize("result, expected", [
        ({"ra": 2.32, "dec": 57.13}, (2.32, 57.13)),   # newer firmware
        ([42.3, 312.7], (42.3, 312.7)),                # older firmware
        ((1, 2, 3), (1, 2)),                           # extra elements ignored
        ({"ra": 2.32}, (2.32, None)),                  # half a pair
        ({}, (None, None)),
        ([1], (None, None)),
        (None, (None, None)),
        ("nonsense", (None, None)),
    ])
    def test_coord_pair(self, result, expected):
        assert status.coord_pair(result, ("ra", "dec")) == expected

    def test_dashboard_uses_the_same_helpers(self):
        """The monitor kept byte-identical copies of these two."""
        from seestarpy.dashboard import monitor

        assert monitor._num is status.as_number
        assert monitor._pair is status.coord_pair


# ---------------------------------------------------------------------------
# One cached firmware accessor, shared by status and stack
# ---------------------------------------------------------------------------

class TestFirmwareVersion:
    def setup_method(self):
        status._firmware_cache.clear()

    def teardown_method(self):
        status._firmware_cache.clear()

    _REPLY = {"result": {"device": {"firmware_ver_string": "8.46",
                                    "firmware_ver_int": 2846}}}

    def test_returns_both_forms(self):
        with patch("seestarpy.raw.get_device_state", return_value=self._REPLY):
            assert status.firmware_version(ip="10.0.0.1") == ("8.46", 2846)

    def test_result_is_cached_per_scope(self):
        with patch("seestarpy.raw.get_device_state",
                   return_value=self._REPLY) as mock:
            status.firmware_version(ip="10.0.0.1")
            status.firmware_version(ip="10.0.0.1")
        mock.assert_called_once()

    def test_refresh_requeries(self):
        with patch("seestarpy.raw.get_device_state",
                   return_value=self._REPLY) as mock:
            status.firmware_version(ip="10.0.0.1")
            status.firmware_version(ip="10.0.0.1", refresh=True)
        assert mock.call_count == 2

    def test_separate_scopes_are_cached_separately(self):
        with patch("seestarpy.raw.get_device_state",
                   return_value=self._REPLY) as mock:
            status.firmware_version(ip="10.0.0.1")
            status.firmware_version(ip="10.0.0.2")
        assert mock.call_count == 2

    def test_a_failure_is_not_cached(self):
        """A scope mid-boot must be retried, not written off for the session."""
        with patch("seestarpy.raw.get_device_state", side_effect=OSError):
            assert status.firmware_version(ip="10.0.0.1") == (None, None)
        assert "10.0.0.1" not in status._firmware_cache

    def test_get_firmware_version_reads_through_it(self):
        with patch("seestarpy.raw.get_device_state", return_value=self._REPLY):
            assert status.get_firmware_version() == "8.46"

    def test_stack_reads_through_it(self):
        """stack.py kept a second cache of the same value."""
        from seestarpy import stack

        with patch("seestarpy.raw.get_device_state", return_value=self._REPLY):
            assert stack._firmware_ver_int("10.0.0.1") == 2846
