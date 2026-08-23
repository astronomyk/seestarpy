"""Unit tests for the polar-alignment keepalive fix.

The firmware ties a 3PPA run to the TCP connection that issued
``start_polar_align`` and closes an idle port-4700 socket after ~15.5 s.
A bare call therefore gets the alignment cancelled ~19 s in, leaving the
mount stopped mid-slew.  ``ui.polar_align`` holds the connection open for
the whole run and blocks until the firmware reports a terminal state.

These tests are offline: the connection layer is mocked, so nothing here
touches a telescope.
"""

import threading
from unittest.mock import patch

import pytest

from seestarpy import connection, ui


class TestPaProgress:
    """The verbose progress renderer turns raw events into one-line status."""

    def test_returns_none_for_unrelated_events(self):
        for frame in ({"Event": "PiStatus"},
                      {"Event": "Exposure", "state": "working"},
                      {"Event": "MoveByAngle", "state": "moving", "value": 3.0},
                      {"Event": "PlateSolve", "page": "preview",
                       "state": "solving"}):
            assert ui._pa_progress(frame) is None

    def test_3ppa_states_are_named_not_numbered(self):
        line = ui._pa_progress({"Event": "3PPA", "state": "move1",
                                "state_code": 5})
        assert "move1" in line and "state_code=5" in line

    def test_unknown_state_code_falls_back_to_state_string(self):
        line = ui._pa_progress({"Event": "3PPA", "state": "wat",
                                "state_code": 99})
        assert "wat" in line

    def test_pa_error_block_is_rendered(self):
        line = ui._pa_progress({
            "Event": "3PPA", "state": "calc3", "state_code": 14,
            "pa_error": {"total": 1.0721, "x": -0.5419, "y": -0.9251,
                         "total_arcsec": 3859.6},
        })
        assert "calc3" in line
        assert "1.0721" in line and "-0.5419" in line and "-0.9251" in line

    def test_goto_failure_surfaces_the_error_code(self):
        line = ui._pa_progress({"Event": "ScopeGoto", "state": "fail",
                                "error": "fail to operate", "code": 207})
        assert "207" in line and "fail to operate" in line

    def test_terminal_eqmodepa_reports_the_result(self):
        line = ui._pa_progress({"Event": "EqModePA", "state": "complete",
                                "total": 0.9209, "x": -0.5768, "y": -0.7179})
        assert "0.9209" in line
        assert ui._pa_progress({"Event": "EqModePA",
                                "state": "cancel"}) == "  CANCEL"

    def test_state_code_ladder_matches_firmware(self):
        assert ui.PA_STATE_CODES == {1: "start", 5: "move1", 6: "delay1",
                                     10: "move2", 11: "delay2",
                                     14: "calc3", 17: "calc4"}


class TestKeepaliveRefCounting:
    """Nested keepalives must share one thread and outlive inner exits."""

    def test_nested_start_stop_keeps_one_thread(self):
        c = connection._Connection("10.0.0.99")
        with patch.object(c, "send"):
            c.start_keepalive(interval=0.01)
            first = c._ka_thread
            assert first is not None and first.is_alive()

            c.start_keepalive()                 # nested
            assert c._ka_thread is first        # same thread reused
            assert c._ka_refs == 2

            c.stop_keepalive()                  # inner exit
            assert c._ka_thread is first        # still running
            assert c._ka_refs == 1

            c.stop_keepalive()                  # outer exit
            assert c._ka_thread is None
            assert not first.is_alive()

    def test_force_stop_clears_all_references(self):
        c = connection._Connection("10.0.0.99")
        with patch.object(c, "send"):
            c.start_keepalive(interval=0.01)
            c.start_keepalive()
            c.stop_keepalive(force=True)
            assert c._ka_thread is None and c._ka_refs == 0

    def test_stop_without_start_is_harmless(self):
        c = connection._Connection("10.0.0.99")
        c.stop_keepalive()          # must not raise
        assert c._ka_thread is None

    def test_keepalive_actually_pings(self):
        c = connection._Connection("10.0.0.99")
        pinged = threading.Event()
        with patch.object(c, "send",
                          side_effect=lambda *a, **k: pinged.set()):
            c.start_keepalive(interval=0.01)
            try:
                assert pinged.wait(2.0), "keepalive never pinged the socket"
            finally:
                c.stop_keepalive()

    def test_ping_interval_stays_under_the_firmware_idle_timeout(self):
        """~15.5 s is when the firmware drops an idle socket."""
        assert 0 < connection.KEEPALIVE_INTERVAL < 15.0

    def test_send_failure_does_not_kill_the_keepalive_thread(self):
        c = connection._Connection("10.0.0.99")
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise ConnectionError("dropped")

        with patch.object(c, "send", side_effect=boom):
            c.start_keepalive(interval=0.01)
            try:
                deadline = threading.Event()
                deadline.wait(0.5)
                assert len(calls) > 1, "thread died on the first failure"
                assert c._ka_thread.is_alive()
            finally:
                c.stop_keepalive()


class TestEventDispatch:
    """A keepalive ping doubles as the event pump for progress reporting."""

    def test_handlers_receive_frames_and_can_be_removed(self):
        c = connection._Connection("10.0.0.99")
        got = []
        h = c.add_event_handler(got.append)
        c._dispatch({"Event": "3PPA"})
        assert got == [{"Event": "3PPA"}]

        c.remove_event_handler(h)
        c._dispatch({"Event": "EqModePA"})
        assert len(got) == 1

    def test_broken_handler_does_not_break_the_read_loop(self):
        c = connection._Connection("10.0.0.99")
        got = []
        c.add_event_handler(lambda f: 1 / 0)
        c.add_event_handler(got.append)
        c._dispatch({"Event": "3PPA"})          # must not raise
        assert got == [{"Event": "3PPA"}]

    def test_removing_an_unregistered_handler_is_harmless(self):
        c = connection._Connection("10.0.0.99")
        c.remove_event_handler(lambda f: None)


class TestPolarAlign:
    """The blocking wrapper: payload, keepalive, and terminal states."""

    @staticmethod
    def _run(events, **kwargs):
        """Drive polar_align with a fake connection that replays *events*."""
        holder = {}

        class FakeConn:
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

        fake = FakeConn()
        holder["conn"] = fake

        def fake_start_pa(**kw):
            holder["payload"] = kw
            # The firmware only emits events once the run has begun.
            for frame in events:
                for h in list(fake.handlers):
                    h(frame)
            return {"code": 0, "result": 0}

        with patch.object(connection, "_get_connection", return_value=fake), \
             patch.object(connection, "current_ip", return_value="10.0.0.99"), \
             patch("seestarpy.ui.raw.start_polar_align",
                   side_effect=fake_start_pa):
            res = ui.polar_align(**kwargs)
        return res, holder

    def test_completion_returns_the_measured_error(self, capsys):
        res, _ = self._run([
            {"Event": "3PPA", "state": "start", "state_code": 1},
            {"Event": "EqModePA", "state": "complete", "total": 1.0721,
             "x": -0.5419, "y": -0.9251, "lapse_ms": 41944},
        ])
        assert res["state"] == "complete"
        assert res["total"] == pytest.approx(1.0721)
        assert res["x"] == pytest.approx(-0.5419)
        assert res["y"] == pytest.approx(-0.9251)
        assert res["lapse_ms"] == 41944

    def test_cancel_is_reported_not_swallowed(self):
        """The bare-call failure mode must surface, not look like success."""
        res, _ = self._run([{"Event": "EqModePA", "state": "cancel",
                             "lapse_ms": 18795}])
        assert res["state"] == "cancel"
        assert res["total"] is None

    def test_timeout_when_the_firmware_never_finishes(self):
        res, _ = self._run([], timeout=0.05)
        assert res["state"] == "timeout"
        assert res["total"] is None

    def test_keepalive_wraps_the_whole_run(self):
        _, h = self._run([{"Event": "EqModePA", "state": "complete",
                           "total": 1.0, "x": 0.0, "y": 0.0,
                           "lapse_ms": 1}])
        assert h["conn"].keepalive_started == 1
        assert h["conn"].keepalive_stopped == 1
        assert h["conn"].handlers == []          # handler cleaned up

    def test_keepalive_released_even_on_timeout(self):
        _, h = self._run([], timeout=0.05)
        assert h["conn"].keepalive_stopped == 1
        assert h["conn"].handlers == []

    def test_restart_and_index_are_forwarded(self):
        _, h = self._run([{"Event": "EqModePA", "state": "complete",
                           "total": 1.0, "x": 0.0, "y": 0.0, "lapse_ms": 1}],
                         dec_pos_index=4)
        assert h["payload"] == {"restart": True, "dec_pos_index": 4}

        _, h = self._run([{"Event": "EqModePA", "state": "complete",
                           "total": 1.0, "x": 0.0, "y": 0.0, "lapse_ms": 1}],
                         restart=False)
        assert h["payload"]["restart"] is False

    def test_verbose_prints_progress_and_quiet_does_not(self, capsys):
        events = [{"Event": "3PPA", "state": "move1", "state_code": 5},
                  {"Event": "EqModePA", "state": "complete", "total": 1.0,
                   "x": 0.0, "y": 0.0, "lapse_ms": 1}]
        self._run(events)
        out = capsys.readouterr().out
        assert "move1" in out and "RESULT" in out

        # verbose=False silences polar_align's own progress lines.  The
        # "<func>: call to <ip>" banner comes from @multiple_ips and is
        # governed by connection.VERBOSE_LEVEL, not by this flag.
        self._run(events, verbose=False)
        out = capsys.readouterr().out
        assert "move1" not in out and "RESULT" not in out
