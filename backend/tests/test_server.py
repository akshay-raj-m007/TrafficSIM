"""HTTP + WebSocket behaviour of the FastAPI adapter (binary vehicle frames + JSON)."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.ws_util import decoded, hello_and_format, next_frame, next_json, recv
from trafficsim.server.app import BAD_REQUEST_CLOSE_CODE, BUSY_CLOSE_CODE, create_app
from trafficsim.server.config import Settings
from trafficsim.server.frames import BYTES_PER_VEHICLE, HEADER

# `signal=uncontrolled` avoids the J1 saturation-flow measurement (about 7 s) in fast tests.
WS = "/ws/sim?signal=uncontrolled"


@pytest.fixture
def client():
    # Fast frame rate keeps the tests quick; semantics are identical to 10 Hz.
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=50.0, warm_up=False))
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["dt"] == 0.1
    assert (body["sessions_active"], body["sessions_max"]) == (0, 1)


def test_network_endpoint_is_gzipped_json(client):
    r = client.get("/api/network", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
    data = r.json()
    assert data["meta"]["units"] == "m"
    assert {j["control"] for j in data["junctions"]} == {"signalised", "give_way"}
    assert len(gzip.compress(r.content)) < len(r.content)


def test_hello_describes_the_session_and_is_followed_by_a_frame(client):
    with client.websocket_connect(WS) as ws:
        hello, fmt = hello_and_format(ws)
        assert hello["dt"] == 0.1 and hello["steps_per_second"] == 10
        assert hello["speeds"] == [0, 0.25, 0.5, 1, 2, 5, 10]
        assert (hello["seed"], hello["signal"], hello["demand_scale"]) == (42, "uncontrolled", 1.0)
        names = [c["name"] for c in hello["classes"]]
        assert names == ["car", "truck_bus", "two_wheeler", "cav"]
        car, truck = hello["classes"][0], hello["classes"][1]
        assert (car["length_m"], car["width_m"], car["height_m"]) == (4.5, 1.8, 1.5)
        assert truck["height_m"] == 3.2
        assert {"flow", "queue", "delay", "unserved", "signal"} <= set(hello["kpi_defs"])
        assert fmt.bytes_per_vehicle == BYTES_PER_VEHICLE and fmt.header_bytes == HEADER.size
        first = decoded(ws, fmt)
        assert (first["tick"], first["n"], first["epoch"]) == (0, 0, 0)


def test_frames_carry_vehicles_and_have_the_documented_size(client):
    with client.websocket_connect(WS) as ws:
        hello, fmt = hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 10}))
        n = 0
        for _ in range(600):
            raw = next_frame(ws)
            n = HEADER.unpack_from(raw)[5]
            assert len(raw) == HEADER.size + BYTES_PER_VEHICLE * n
            if n >= 5:
                break
        assert n >= 5
        f = decoded(ws, fmt)
        assert f["seg"].max() < len(hello["segments"]) and (f["speed"] <= 17).all()


def test_frames_are_sent_only_when_the_simulation_advanced(client):
    """At 0.25x and 50 Hz a tick takes 20 wall frames; no duplicate frames in between."""
    with client.websocket_connect(WS) as ws:
        _, fmt = hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 0.25}))
        ticks = []
        while len(ticks) < 4:
            f = decoded(ws, fmt)
            if f["speed_index"] == 1:  # 0.25x
                ticks.append(f["tick"])
        assert [b - a for a, b in zip(ticks, ticks[1:], strict=False)] == [1, 1, 1]


def test_pause_stops_frames_but_stats_continue(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 0}))
        stats = []
        while len(stats) < 2 or stats[-1]["speed"] != 0:
            m = recv(ws)
            if isinstance(m, dict) and m["type"] == "stats":
                stats.append(m)
        later = next_json(ws, "stats")  # another one arrives: the session is alive
        assert later["tick"] == stats[-1]["tick"] and later["frames"] == 0


def test_kpi_and_stats_messages(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 10}))
        kpi = next_json(ws, "kpi")
        stats = next_json(ws, "stats")
        assert {"counts", "flow", "queues", "delay", "unserved", "signal"} <= set(kpi)
        assert len(kpi["flow"]) == 12 and len(kpi["queues"]) == 7
        assert kpi["signal"] is None  # uncontrolled session
        for k in ("frame_bytes_mean", "bytes_per_s", "step_ms_mean", "encode_ms_mean", "vehicles"):
            assert k in stats
        assert stats["lag_ms"] >= 0


def test_reset_bumps_the_epoch_and_restarts(client):
    with client.websocket_connect(WS) as ws:
        _, fmt = hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 10}))
        for _ in range(5):
            next_frame(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 0}))
        ws.send_text(json.dumps({"type": "reset", "seed": 7}))
        hello = next_json(ws, "hello")
        assert hello["seed"] == 7 and hello["epoch"] == 1
        f = decoded(ws, fmt)
        assert f["epoch"] == 1 and f["tick"] == 0


def test_speed_ping_and_invalid_messages(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 3}))  # not an allowed speed
        ws.send_text("not json")
        ws.send_text(json.dumps({"type": "ping", "id": 99}))
        seen = []
        while not {"pong", "error"} <= {m["type"] for m in seen}:
            m = recv(ws)
            if isinstance(m, dict) and m["type"] in ("pong", "error"):
                seen.append(m)
        assert sum(m["type"] == "error" for m in seen) == 2  # bad speed and bad JSON
        assert next(m for m in seen if m["type"] == "pong")["id"] == 99


@pytest.mark.parametrize(
    "query", ["signal=bogus", "demand_scale=9", "demand_scale=0.01", "seed=-1"]
)
def test_bad_session_parameters_are_rejected(client, query):
    with client.websocket_connect(f"/ws/sim?{query}") as ws:
        assert next_json(ws, "error")
        with pytest.raises(WebSocketDisconnect) as exc:
            recv(ws)
        assert exc.value.code == BAD_REQUEST_CLOSE_CODE


def test_session_cap_rejects_with_busy_and_1013(client):
    with client.websocket_connect(WS) as first:
        hello_and_format(first)
        assert client.get("/api/health").json()["sessions_active"] == 1
        with client.websocket_connect(WS) as second:
            msg = recv(second)
            assert msg["type"] == "busy"
            text = msg["message"].lower()  # friendly: says what to do and what still works
            assert "try again in a minute" in text and "compare" in text and "validation" in text
            with pytest.raises(WebSocketDisconnect) as exc:
                recv(second)
            assert exc.value.code == BUSY_CLOSE_CODE
        assert client.get("/api/health").json()["sessions_rejected_total"] == 1


def test_slot_is_released_after_disconnect(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
    with client.websocket_connect(WS) as ws:  # would be busy if not released
        assert next_json(ws, "hello")["type"] == "hello"
