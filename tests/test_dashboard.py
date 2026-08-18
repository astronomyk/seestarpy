"""Unit tests for the multi-Seestar web dashboard.

The dashboard has to survive the two things a fleet of Seestars reliably
does: answer the same query with a different shape on every firmware
version, and go quiet at the worst moment.  These tests pin down the
snapshot builder (which turns whatever the firmware said into the card
payload), the image pipeline (stretch and encode), and the HTTP layer —
all without touching a telescope.
"""

import json
import socket
import threading
import urllib.error
import urllib.request

import pytest

from seestarpy import stream
from seestarpy.dashboard import monitor as mon
from seestarpy.dashboard.server import DashboardServer

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _device_state(**overrides):
    state = {
        "device": {"product_model": "Seestar S50", "sn": "a3497936",
                   "firmware_ver_string": "7.75", "focal_len": 250.0},
        "setting": {"exp_ms": {"stack_l": 10000, "continuous": 500},
                    "stack_dither": {"pix": 50, "interval": 5, "enable": True}},
        "mount": {"equ_mode": True, "tracking": True, "close": False},
        "pi_status": {"temp": 41.5, "battery_capacity": 62,
                      "charge_online": False},
        "station": {"ip": "192.168.1.55"},
        "storage": {"storage_volume": [{"free_mb": 36549, "total_mb": 51854}]},
    }
    state.update(overrides)
    return state


def _app_state():
    return {
        "View": {
            "state": "working", "stage": "Stack", "mode": "star",
            "target_name": "NGC 869", "target_ra_dec": [2.32, 57.13],
            "gain": 80, "lp_filter": False,
            "Stack": {"state": "working", "stacked_frame": 204,
                      "dropped_frame": 6,
                      "Exposure": {"exp_ms": 10000}},
        }
    }


def _monitor(ip="192.168.1.55", **rpc):
    """A ScopeMonitor pre-loaded with RPC results, with no threads running."""
    m = mon.ScopeMonitor(sn="a3497936", ip=ip, model="Seestar S50",
                         dev_id="s50_a3497936")
    m._rpc = {"get_device_state": _device_state(),
              "iscope_get_app_state": _app_state(),
              "scope_get_equ_coord": {"ra": 2.3201, "dec": 57.1334},
              "scope_get_horiz_coord": [42.31, 312.7],
              "get_wheel_position": 1}
    m._rpc.update(rpc)
    m._connected = True
    return m


# ---------------------------------------------------------------------------
# Snapshot: firmware shape tolerance
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_builds_the_full_card_payload(self):
        s = _monitor().snapshot()
        assert s["sn"] == "a3497936"
        assert s["model"] == "Seestar S50"
        assert s["exp_s"] == 10.0
        assert s["stacked_frames"] == 204
        assert s["dropped_frames"] == 6
        assert s["dropped_pct"] == pytest.approx(2.9, abs=0.05)
        assert s["stack_time_s"] == 2040
        assert s["filter"] == "IRCUT"
        assert s["target"] == "NGC 869"
        assert s["battery"] == 62
        assert s["free_gb"] == pytest.approx(35.7, abs=0.1)
        assert s["equ_mode"] is True

    def test_horizontal_coords_as_a_list(self):
        """Firmware 7.75/8.46 answer scope_get_horiz_coord with [alt, az]."""
        s = _monitor().snapshot()
        assert s["alt"] == pytest.approx(42.3)      # rounded for display
        assert s["az"] == pytest.approx(312.7)
        assert s["compass"] == "NW"

    def test_horizontal_coords_as_a_dict(self):
        """Older firmware answers with a dict; both must work."""
        s = _monitor(scope_get_horiz_coord={"alt": 10.0, "az": 90.0}).snapshot()
        assert (s["alt"], s["az"]) == (10.0, 90.0)
        assert s["compass"] == "E"

    def test_unreadable_values_become_none_not_crashes(self):
        """An error reply must dash out one field, not take the card down."""
        m = _monitor()
        m._rpc["scope_get_horiz_coord"] = {"error": "method not found"}
        m._rpc["get_device_state"] = {}
        s = m.snapshot()
        assert s["alt"] is None and s["az"] is None and s["compass"] is None
        assert s["battery"] is None and s["free_gb"] is None
        # The View block is independent, so it still reports.
        assert s["target"] == "NGC 869"

    def test_snapshot_is_json_serialisable(self):
        """It goes straight down an SSE stream, so it must serialise."""
        json.dumps(_monitor().snapshot())

    def test_snapshot_never_calls_the_network(self, monkeypatch):
        """snapshot() runs once a second per browser; it must stay offline."""
        def boom(*_a, **_kw):
            raise AssertionError("snapshot() made a network call")

        monkeypatch.setattr("seestarpy.connection.send_command", boom)
        m = _monitor()
        # focal_len missing is the case that used to fall through to a query
        m._rpc["get_device_state"]["device"].pop("focal_len")
        s = m.snapshot()
        assert s["dither"] == "50 px /5 sub"

    def test_dither_reported_in_arcminutes_when_focal_length_is_known(self):
        # 50 px * 2.39 "/px / 60 = 1.99'
        assert _monitor().snapshot()["dither"] == "2.0' /5 sub"

    def test_events_override_polled_state(self):
        """A Stack event is fresher than the polled app-state block."""
        m = _monitor()
        m._events["Stack"] = {"Event": "Stack", "state": "working",
                              "stacked_frame": 300, "dropped_frame": 0}
        s = m.snapshot()
        assert s["stacked_frames"] == 300
        assert s["dropped_frames"] == 0

    def test_transfer_mode_defaults_to_raw_without_a_preview_block(self):
        """Firmware before 8.46 has no preview setting and always sends Raw."""
        assert _monitor().snapshot()["transfer_mode"] == "Raw"

    def test_transfer_mode_is_read_from_the_preview_block(self):
        m = _monitor()
        m._rpc["get_device_state"]["setting"]["preview"] = {
            "image_transfer_mode": "Jpg", "rtsp_quality": "HighQuality"}
        assert m.snapshot()["transfer_mode"] == "Jpg"

    def test_link_is_wifi_when_the_station_ip_matches(self):
        assert _monitor(ip="192.168.1.55").snapshot()["link"] == "wifi"

    def test_link_is_lan_when_talking_on_another_address(self):
        """A different address means the USB-C Ethernet gadget is carrying it."""
        assert _monitor(ip="192.168.1.83").snapshot()["link"] == "lan"


# ---------------------------------------------------------------------------
# Image pipeline
# ---------------------------------------------------------------------------

class TestAutoStretch:
    def _sky(self, median=1300, noise=20, shape=(64, 64, 3)):
        rng = np.random.default_rng(0)
        return (rng.normal(median, noise, shape)).astype(np.uint16)

    def test_puts_the_sky_background_on_target(self):
        """The whole point: a faint frame comes out visible, not black."""
        out = stream.auto_stretch(self._sky(), target_bg=0.15)
        assert out.dtype == np.uint8
        assert np.median(out) == pytest.approx(0.15 * 255, abs=12)

    def test_target_is_honoured(self):
        sky = self._sky()
        dark = np.median(stream.auto_stretch(sky, target_bg=0.10))
        bright = np.median(stream.auto_stretch(sky, target_bg=0.30))
        assert dark < bright

    def test_independent_of_the_absolute_signal_level(self):
        """Gain and sky brightness must not change how bright the card looks."""
        faint = np.median(stream.auto_stretch(self._sky(median=1300, noise=20)))
        bright = np.median(stream.auto_stretch(self._sky(median=9000, noise=140)))
        assert faint == pytest.approx(bright, abs=12)

    def test_flat_frame_does_not_divide_by_zero(self):
        flat = np.full((16, 16, 3), 1000, dtype=np.uint16)
        out = stream.auto_stretch(flat)
        assert out.shape == (16, 16, 3)
        assert np.isfinite(out).all()


class TestBlockReduce:
    def test_averages_blocks(self):
        arr = np.arange(16, dtype=np.float32).reshape(4, 4)
        out = mon._block_reduce(arr, 2)
        assert out.shape == (2, 2)
        assert out[0, 0] == pytest.approx(2.5)   # mean of 0,1,4,5

    def test_crops_a_ragged_edge_rather_than_failing(self):
        assert mon._block_reduce(np.zeros((5, 7)), 2).shape == (2, 3)

    def test_factor_one_is_a_no_op(self):
        arr = np.zeros((4, 4))
        assert mon._block_reduce(arr, 1) is arr


class TestEncodeFrame:
    def _header(self, w, h, img_type):
        return {"width": w, "height": h, "img_type": img_type, "image_id": 7}

    def test_encodes_an_uncompressed_stacked_rgb_frame(self):
        """The S30 Pro / firmware 7.75 shape: raw 48bpp, no ZIP wrapper."""
        w, h = 64, 96
        payload = np.full((h, w, 3), 1200, dtype=np.uint16).tobytes()
        jpeg, size = mon.encode_frame(self._header(w, h, 5), payload,
                                      long_side=48)
        assert jpeg.startswith(b"\xff\xd8")     # JPEG SOI
        assert size == (w, h)

    def test_encodes_a_raw_bayer_preview_frame(self):
        w, h = 64, 96
        payload = np.full((h, w), 1200, dtype=np.uint16).tobytes()
        jpeg, size = mon.encode_frame(self._header(w, h, 1), payload,
                                      long_side=48)
        assert jpeg.startswith(b"\xff\xd8")
        assert size == (w, h)

    def test_rejects_an_ack_frame(self):
        with pytest.raises(ValueError):
            mon.encode_frame(self._header(0, 0, 0), b"")

    def test_downsamples_towards_the_target(self):
        w, h = 200, 400
        payload = np.full((h, w, 3), 1200, dtype=np.uint16).tobytes()
        jpeg, _ = mon.encode_frame(self._header(w, h, 5), payload,
                                   long_side=100)
        from PIL import Image
        import io
        assert max(Image.open(io.BytesIO(jpeg)).size) <= 100


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

class _FakeFleet:
    """Stands in for Fleet so the server can be tested with no telescopes."""

    def __init__(self, monitors=()):
        self._monitors = {m.sn: m for m in monitors}

    def start(self):
        pass

    def stop(self):
        pass

    def get(self, sn):
        return self._monitors.get(sn)

    def snapshot(self):
        return {"scopes": [m.snapshot() for m in self._monitors.values()],
                "scanned_at": 1.0, "server_time": 2.0}


@pytest.fixture
def server():
    m = _monitor()
    m._jpeg = b"\xff\xd8\xff\xd9"
    m._frame_seq = 3
    srv = DashboardServer(host="127.0.0.1", port=0)
    srv.fleet = _FakeFleet([m])
    srv.start()
    # port=0 asks the OS for a free port; read back the one it gave us.
    srv.port = srv._httpd.server_address[1]
    yield srv
    srv.stop()


def _get(server, path):
    return urllib.request.urlopen(
        f"http://127.0.0.1:{server.port}{path}", timeout=5)


class TestServer:
    def test_serves_the_page(self, server):
        response = _get(server, "/")
        assert response.status == 200
        assert b"Seestar Dashboard" in response.read()

    def test_serves_the_assets(self, server):
        assert _get(server, "/dashboard.css").status == 200
        assert _get(server, "/dashboard.js").status == 200

    def test_scopes_endpoint_returns_the_fleet(self, server):
        payload = json.load(_get(server, "/api/scopes"))
        assert [s["sn"] for s in payload["scopes"]] == ["a3497936"]

    def test_image_endpoint_returns_the_latest_jpeg(self, server):
        response = _get(server, "/api/image/a3497936")
        assert response.headers["Content-Type"] == "image/jpeg"
        assert response.read() == b"\xff\xd8\xff\xd9"

    def test_image_endpoint_404s_for_an_unknown_scope(self, server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(server, "/api/image/nosuchscope")
        assert exc.value.code == 404

    def test_image_endpoint_204s_before_the_first_frame(self, server):
        server.fleet.get("a3497936")._jpeg = None
        assert _get(server, "/api/image/a3497936").status == 204

    def test_static_serving_refuses_to_escape_its_directory(self, server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(server, "/..%2f..%2fsetup.py")
        assert exc.value.code == 404

    def test_events_endpoint_pushes_sse_frames(self, server):
        response = _get(server, "/api/events")
        assert response.headers["Content-Type"].startswith("text/event-stream")
        line = response.readline().decode()
        assert line.startswith("data: ")
        assert json.loads(line[len("data: "):])["scopes"][0]["sn"] == "a3497936"
        response.close()


class _SilentSocket:
    """A socket that accepts writes and never has anything to read."""

    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _n):
        raise socket.timeout()


class TestCommandLoop:
    def test_heartbeats_keep_going_while_the_scope_is_quiet(self, monkeypatch):
        """An idle scope emits nothing between replies.

        The read loop must not block on recv until the liveness timeout,
        or every parked scope would drop its connection every 45 s.
        """
        monkeypatch.setattr(mon, "HEARTBEAT_INTERVAL", 0.0)
        monkeypatch.setattr(mon, "SOCKET_TIMEOUT", 0.25)
        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        sock = _SilentSocket()

        with pytest.raises(ConnectionError):
            m._read_events(sock)

        assert len(sock.sent) > 1, "loop blocked instead of heartbeating"
        methods = [json.loads(s.decode())["method"] for s in sock.sent]
        # It walks the cycle rather than re-asking the same thing.
        assert methods[0] == "get_device_state"
        assert len(set(methods)) > 1

    def test_silence_eventually_forces_a_reconnect(self, monkeypatch):
        monkeypatch.setattr(mon, "HEARTBEAT_INTERVAL", 0.0)
        monkeypatch.setattr(mon, "SOCKET_TIMEOUT", 0.1)
        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        with pytest.raises(ConnectionError, match="silent"):
            m._read_events(_SilentSocket())

    def test_closed_socket_forces_a_reconnect(self):
        class _Closed(_SilentSocket):
            def recv(self, _n):
                return b""

        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        with pytest.raises(ConnectionError, match="closed"):
            m._read_events(_Closed())

    def test_routes_events_and_rpc_results_separately(self):
        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        m._handle_message('{"Event": "Stack", "state": "working"}')
        m._handle_message('{"method": "scope_get_equ_coord", '
                          '"result": {"ra": 1.0, "dec": 2.0}}')
        assert m._events["Stack"]["state"] == "working"
        assert m._rpc["scope_get_equ_coord"] == {"ra": 1.0, "dec": 2.0}

    def test_garbage_lines_are_ignored(self):
        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        m._handle_message("not json at all")
        m._handle_message("[1, 2, 3]")
        assert m._events == {} and m._rpc == {}


class TestMissingImagingDeps:
    def test_reported_on_the_card_and_not_wiped_by_a_reconnect(self, monkeypatch):
        """The message must survive the command loop's reconnects."""
        def no_imaging():
            raise ImportError("install numpy and pillow")

        monkeypatch.setattr(mon, "_require_imaging", no_imaging)
        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        m._image_loop()
        m._set_connected(True)          # what a successful reconnect does
        assert "numpy" in m.snapshot()["image_error"]


class TestBindDefaults:
    """The dashboard has no auth, so it must not reach the LAN by accident."""

    def test_defaults_to_loopback(self):
        assert DashboardServer().host == "127.0.0.1"

    def test_lan_flag_opens_it_up(self):
        assert DashboardServer(lan=True).host == "0.0.0.0"

    def test_explicit_host_overrides_lan(self):
        assert DashboardServer(host="10.1.2.3", lan=True).host == "10.1.2.3"


class TestMonitorLifecycle:
    def test_start_is_idempotent(self, monkeypatch):
        """Two start() calls must not give one scope four threads."""
        monkeypatch.setattr(mon.ScopeMonitor, "_command_loop",
                            lambda self: self._stop.wait(30))
        monkeypatch.setattr(mon.ScopeMonitor, "_image_loop",
                            lambda self: self._stop.wait(30))
        m = mon.ScopeMonitor(sn="x", ip="127.0.0.1")
        before = threading.active_count()
        m.start()
        m.start()
        assert threading.active_count() == before + 2
        m.stop()

    def test_set_ip_updates_the_target(self):
        m = mon.ScopeMonitor(sn="x", ip="192.168.1.5")
        m.set_ip("192.168.1.9")
        assert m.ip == "192.168.1.9"
        assert m.snapshot()["ip"] == "192.168.1.9"
