"""Unit tests for the blocking operation wrappers in :mod:`seestarpy.ui`.

``polar_align``, ``autofocus``, ``goto`` and ``goto_target`` all wrap a
firmware operation that is tied to the TCP connection that issued it: the
command goes out inside a ``connection.keepalive``, progress events are
rendered as they arrive, and the call blocks until the firmware reports a
terminal state.  ``polar_align``'s own tests live in test_polar_align.py;
this file covers the shared machinery and the other three wrappers.

Offline: the connection layer is mocked, so nothing here touches a scope.
"""

import ast
import os
from unittest.mock import patch

import pytest

from seestarpy import connection, ui


# --------------------------------------------------------------------------
# Shared fake-connection harness
# --------------------------------------------------------------------------
class FakeConn:
    """Stands in for a pooled _Connection, replaying events on start."""

    def __init__(self):
        self.handlers = []
        self.keepalive_started = 0
        self.keepalive_stopped = 0

    def add_event_handler(self, fn):
        self.handlers.append(fn)
        return fn

    def remove_event_handler(self, fn):
        self.handlers.remove(fn)

    def start_keepalive(self, interval=None):
        self.keepalive_started += 1

    def stop_keepalive(self, force=False):
        self.keepalive_stopped += 1

    def emit(self, events):
        for frame in events:
            for h in list(self.handlers):
                h(frame)


def run_op(fn, events, rpc_targets, **kwargs):
    """Call *fn*, replaying *events* when any of *rpc_targets* is invoked.

    *rpc_targets* are dotted names of the seestarpy.ui.raw functions the
    wrapper is expected to call to start the operation.
    """
    fake = FakeConn()
    calls = {}

    def starter(name):
        def _inner(*a, **kw):
            calls[name] = (a, kw)
            fake.emit(events)
            return {"code": 0, "result": 0}
        return _inner

    stack = [
        patch.object(connection, "_get_connection", return_value=fake),
        patch.object(connection, "current_ip", return_value="10.0.0.99"),
    ]
    for t in rpc_targets:
        stack.append(patch(f"seestarpy.ui.raw.{t}", side_effect=starter(t)))
    for p in stack:
        p.start()
    try:
        res = fn(**kwargs)
    finally:
        for p in reversed(stack):
            p.stop()
    return res, fake, calls


# --------------------------------------------------------------------------
# _is_outer, validated against the captured event corpus
# --------------------------------------------------------------------------
_CORPUS = os.path.join(os.path.dirname(__file__), "event_output_20250722.dat")


def _corpus_events():
    if not os.path.isfile(_CORPUS):
        return []
    out = []
    with open(_CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(ast.literal_eval(line))
            except (ValueError, SyntaxError):
                continue
    return out


class TestIsOuter:
    """The firmware reports a finished operation twice; only one is final."""

    def test_inner_frames_carry_page(self):
        assert not ui._is_outer({"Event": "AutoGoto", "page": "preview",
                                 "state": "complete"})

    def test_bare_error_frame_is_inner(self):
        assert not ui._is_outer({"Event": "AutoFocus", "state": "fail",
                                 "error": "no star is detected", "code": 279})

    def test_route_or_lapse_marks_the_outer_frame(self):
        assert ui._is_outer({"Event": "AutoFocus", "state": "fail",
                             "code": 279, "lapse_ms": 24182,
                             "route": ["View"]})
        assert ui._is_outer({"Event": "ScopeGoto", "state": "complete",
                             "lapse_ms": 7074})

    @pytest.mark.skipif(not os.path.isfile(_CORPUS), reason="no corpus file")
    def test_every_corpus_terminal_classifies_consistently(self):
        """A page-bearing frame is never outer; an outer always has route/lapse."""
        events = _corpus_events()
        assert events, "corpus parsed empty"
        seen = 0
        for e in events:
            if e.get("state") not in ("complete", "fail", "cancel"):
                continue
            seen += 1
            outer = ui._is_outer(e)
            if outer:
                assert "page" not in e
                assert "route" in e or "lapse_ms" in e
            else:
                assert "page" in e or not ("route" in e or "lapse_ms" in e)
        assert seen > 10, f"only {seen} terminal events exercised"


# --------------------------------------------------------------------------
# _await_operation
# --------------------------------------------------------------------------
class TestAwaitOperation:

    def test_inner_terminal_does_not_end_the_wait_but_is_the_fallback(self):
        """An inner frame is provisional: used only if no outer ever lands."""
        res, fake, _ = run_op(
            ui.autofocus,
            [{"Event": "AutoFocus", "state": "fail",
              "error": "no star is detected", "code": 279}],   # inner only
            ["start_auto_focuse", "get_focuser_position"],
            timeout=0.05,
        )
        assert res["state"] == "fail"
        assert res["error"] == "no star is detected"
        assert res["code"] == 279

    def test_outer_terminal_wins_over_a_preceding_inner(self):
        res, _, _ = run_op(
            ui.autofocus,
            [{"Event": "AutoFocus", "state": "fail", "error": "inner",
              "code": 1},
             {"Event": "AutoFocus", "state": "complete", "lapse_ms": 25634,
              "route": ["View"]}],
            ["start_auto_focuse", "get_focuser_position"],
        )
        assert res["state"] == "complete"
        assert res["lapse_ms"] == 25634

    def test_all_result_fields_present_on_timeout(self):
        res, _, _ = run_op(ui.autofocus, [],
                           ["start_auto_focuse", "get_focuser_position"],
                           timeout=0.05)
        assert res["state"] == "timeout"
        for k in ("lapse_ms", "error", "code", "position"):
            assert k in res, f"missing {k}"

    def test_keepalive_always_released(self):
        _, fake, _ = run_op(ui.autofocus, [],
                            ["start_auto_focuse", "get_focuser_position"],
                            timeout=0.05)
        assert fake.keepalive_started == 1
        assert fake.keepalive_stopped == 1
        assert fake.handlers == []

    def test_quiet_events_are_never_rendered(self, capsys):
        run_op(ui.autofocus,
               [{"Event": "PiStatus", "battery_capacity": 42},
                {"Event": "AutoFocus", "state": "complete", "lapse_ms": 1,
                 "route": []}],
               ["start_auto_focuse", "get_focuser_position"])
        out = capsys.readouterr().out
        assert "battery" not in out and "PiStatus" not in out


# --------------------------------------------------------------------------
# autofocus
# --------------------------------------------------------------------------
class TestAutofocus:

    _OK = [{"Event": "AutoFocus", "state": "start"},
           {"Event": "AutoFocus", "state": "working",
            "result": {"points": [[1620, 4.05], [1630, 3.14]]}},
           {"Event": "AutoFocus", "state": "complete", "lapse_ms": 25634,
            "route": ["View"]}]

    def test_completion_reads_back_the_focuser_position(self):
        res, _, calls = run_op(ui.autofocus, self._OK,
                               ["start_auto_focuse", "get_focuser_position"])
        assert res["state"] == "complete"
        assert "start_auto_focuse" in calls
        assert "position" in res

    def test_verbose_shows_the_fwhm_sweep(self, capsys):
        run_op(ui.autofocus, self._OK,
               ["start_auto_focuse", "get_focuser_position"])
        out = capsys.readouterr().out
        assert "1630" in out and "3.14" in out       # newest sweep point
        assert "FOCUSED" in out

    def test_quiet(self, capsys):
        run_op(ui.autofocus, self._OK,
               ["start_auto_focuse", "get_focuser_position"], verbose=False)
        out = capsys.readouterr().out
        assert "FOCUSED" not in out and "fwhm" not in out

    def test_no_star_failure_is_reported(self):
        res, _, _ = run_op(
            ui.autofocus,
            [{"Event": "AutoFocus", "state": "fail",
              "error": "no star is detected", "code": 279,
              "lapse_ms": 24182, "route": ["View", "Initialise"]}],
            ["start_auto_focuse", "get_focuser_position"])
        assert res["state"] == "fail" and res["code"] == 279

    def test_focuser_readback_failure_is_survivable(self):
        """A broken position read must not lose the focus result."""
        fake = FakeConn()
        with patch.object(connection, "_get_connection", return_value=fake), \
             patch.object(connection, "current_ip", return_value="10.0.0.99"), \
             patch("seestarpy.ui.raw.start_auto_focuse",
                   side_effect=lambda *a, **k: fake.emit(self._OK)), \
             patch("seestarpy.ui.raw.get_focuser_position",
                   side_effect=OSError("boom")):
            res = ui.autofocus()
        assert res["state"] == "complete"
        assert res["position"] is None


# --------------------------------------------------------------------------
# goto
# --------------------------------------------------------------------------
class TestGoto:

    def test_radec_waits_on_scopegoto(self):
        res, _, calls = run_op(
            ui.goto,
            [{"Event": "ScopeGoto", "state": "complete", "lapse_ms": 32593,
              "cur_ra_dec": [13.4, 54.9], "dist_deg": 0.0024}],
            ["scope_goto"], ra_dec=(13.4, 54.9))
        assert res["state"] == "complete"
        assert res["cur_ra_dec"] == [13.4, 54.9]
        assert calls["scope_goto"][0] == (13.4, 54.9)

    def test_park_waits_on_scopehome(self):
        res, _, calls = run_op(
            ui.goto,
            [{"Event": "ScopeHome", "state": "complete", "lapse_ms": 18672,
              "close": True, "equ_mode": True}],
            ["scope_park"], ra_dec="park")
        assert res["state"] == "complete"
        assert "scope_park" in calls

    def test_horizon_waits_on_movetohorizon(self):
        res, _, calls = run_op(
            ui.goto,
            [{"Event": "ScopeMoveToHorizon", "state": "complete",
              "lapse_ms": 16826, "close": False}],
            ["scope_move_to_horizon"], ra_dec="horizon")
        assert res["state"] == "complete"
        assert "scope_move_to_horizon" in calls

    def test_park_is_not_ended_by_a_scopegoto_event(self):
        """Each branch must wait on its own terminal event, not any move."""
        res, _, _ = run_op(
            ui.goto,
            [{"Event": "ScopeGoto", "state": "complete", "lapse_ms": 1}],
            ["scope_park"], ra_dec="park", timeout=0.05)
        assert res["state"] == "timeout"

    @pytest.mark.parametrize("bad", ["parkk", "", "nonsense", 42, (1, 2, 3)])
    def test_bad_argument_still_raises(self, bad):
        with pytest.raises(ValueError, match="ra_dec must be one of"):
            ui.goto(ra_dec=bad)

    def test_failure_surfaces_error_and_code(self):
        res, _, _ = run_op(
            ui.goto,
            [{"Event": "ScopeGoto", "state": "fail",
              "error": "mount goto failed", "code": 501, "lapse_ms": 596}],
            ["scope_goto"], ra_dec=(1.0, 2.0))
        assert res["state"] == "fail"
        assert res["error"] == "mount goto failed" and res["code"] == 501


# --------------------------------------------------------------------------
# goto_target
# --------------------------------------------------------------------------
class TestGotoTarget:

    _OK = [{"Event": "AutoGoto", "state": "start",
            "target_name": "NGC 3310"},
           {"Event": "AutoGoto", "page": "preview", "state": "complete"},
           {"Event": "AutoGoto", "state": "complete", "lapse_ms": 31051,
            "count": 2, "hint": False, "route": ["View"]}]

    def test_explicit_coords_are_passed_through_and_echoed(self):
        res, _, calls = run_op(ui.goto_target, self._OK,
                               ["iscope_start_view"],
                               target_name="NGC 3310", ra=10.63, dec=53.5)
        assert res["state"] == "complete"
        assert res["count"] == 2
        assert (res["target_name"], res["ra"], res["dec"]) == \
               ("NGC 3310", 10.63, 53.5)
        assert calls["iscope_start_view"][0] == (10.63, 53.5, "NGC 3310", False)

    def test_name_is_resolved_when_coords_omitted(self):
        with patch("seestarpy.ui.resolve_name", return_value=(10.63, 53.5)) as r:
            res, _, calls = run_op(ui.goto_target, self._OK,
                                   ["iscope_start_view"],
                                   target_name="NGC 3310")
        r.assert_called_once_with("NGC 3310")
        assert res["ra"] == 10.63 and res["dec"] == 53.5

    def test_half_specified_coords_still_raise(self):
        with pytest.raises(ValueError, match="Provide both ra and dec"):
            ui.goto_target("NGC 3310", ra=10.63)

    def test_inner_page_complete_does_not_end_the_wait(self):
        """Only AutoGoto's own frame means the slew-and-solve loop is done."""
        res, _, _ = run_op(ui.goto_target,
                           [{"Event": "AutoGoto", "page": "preview",
                             "state": "complete"}],
                           ["iscope_start_view"],
                           target_name="X", ra=1.0, dec=2.0, timeout=0.05)
        assert res["state"] == "complete"      # provisional fallback
        assert res["count"] is None            # outer detail never arrived

    def test_verbose_reports_arrival_once(self, capsys):
        run_op(ui.goto_target, self._OK, ["iscope_start_view"],
               target_name="NGC 3310", ra=10.63, dec=53.5)
        out = capsys.readouterr().out
        assert out.count("ARRIVED") == 1       # inner frame must not double it
        assert "NGC 3310" in out

    def test_solve_failure_is_reported(self):
        res, _, _ = run_op(
            ui.goto_target,
            [{"Event": "AutoGoto", "state": "fail", "error": "solve failed",
              "code": 251, "lapse_ms": 20678, "count": 7, "hint": False,
              "route": ["View"]}],
            ["iscope_start_view"], target_name="X", ra=1.0, dec=2.0)
        assert res["state"] == "fail" and res["code"] == 251


# --------------------------------------------------------------------------
# progress rendering for the newly-covered events
# --------------------------------------------------------------------------
class TestProgressRendering:

    def test_alert_is_surfaced(self):
        line = ui._pa_progress({"Event": "Alert", "error": "below horizon",
                                "code": 270})
        assert "below horizon" in line and "270" in line

    def test_routine_207_tracking_noise_is_dropped(self):
        assert ui._pa_progress({"Event": "ScopeTrack", "state": "off",
                                "error": "fail to operate",
                                "code": 207}) is None

    def test_real_tracking_error_is_shown(self):
        line = ui._pa_progress({"Event": "ScopeTrack", "state": "off",
                                "error": "below horizon", "code": 270})
        assert "below horizon" in line

    def test_focuser_move_is_too_chatty_to_render(self):
        assert ui._pa_progress({"Event": "FocuserMove", "state": "complete",
                                "position": 1580, "lapse_ms": 1}) is None

    def test_scopegoto_complete_reports_distance(self):
        line = ui._pa_progress({"Event": "ScopeGoto", "state": "complete",
                                "lapse_ms": 1052,
                                "cur_ra_dec": [13.3997, 54.9],
                                "dist_deg": 0.002394})
        assert "13.399" in line and "0.1'" in line

    def test_event_key_spelling_is_tolerated(self):
        """The wire says 'Event'; the captured corpus says 'event'."""
        assert ui._event_name({"event": "AutoFocus"}) == "AutoFocus"
        assert ui._event_name({"Event": "AutoFocus"}) == "AutoFocus"
        assert ui._pa_progress({"event": "AutoFocus", "state": "start"})


class TestRepeatCollapsing:
    """A retrying AutoGoto re-emits the same line; it must not bury the rest."""

    def test_consecutive_repeats_get_a_counter(self, capsys):
        run_op(ui.goto,
               [{"Event": "ScopeGoto", "state": "working"},
                {"Event": "ScopeGoto", "state": "working"},
                {"Event": "ScopeGoto", "state": "working"},
                {"Event": "ScopeGoto", "state": "complete", "lapse_ms": 100}],
               ["scope_goto"], ra_dec=(1.0, 2.0))
        out = capsys.readouterr().out
        assert out.count("slewing   ...") == 3      # each line still appears
        assert "(x2)" in out and "(x3)" in out      # but flagged as repeats
        assert "slewed" in out

    def test_distinct_lines_are_not_collapsed(self, capsys):
        run_op(ui.goto,
               [{"Event": "ScopeGoto", "state": "working"},
                {"Event": "ScopeGoto", "state": "complete", "lapse_ms": 700},
                {"Event": "ScopeGoto", "state": "working"},
                {"Event": "ScopeGoto", "state": "complete", "lapse_ms": 1300}],
               ["scope_goto"], ra_dec=(1.0, 2.0))
        out = capsys.readouterr().out
        assert "(x" not in out


class TestSolveFailureRendering:
    def test_solve_failure_shows_error_and_code(self):
        line = ui._pa_progress({"Event": "PlateSolve", "state": "fail",
                                "error": "solve failed", "code": 251,
                                "lapse_ms": 30961})
        assert "solve failed" in line and "251" in line
