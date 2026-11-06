"""HTTP + WebSocket behaviour of the FastAPI adapter."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from trafficsim.server.app import BUSY_CLOSE_CODE, create_app
from trafficsim.server.config import Settings


@pytest.fixture
def client():
    # Fast frame rate keeps the tests quick; semantics are identical to 10 Hz.
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=50.0))
    with TestClient(app) as c:
        yield c


def _next_tick(ws) -> dict:
    while True:
        msg = ws.receive_json()
        if msg["type"] == "tick":
            return msg


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["dt"] == 0.1
    assert (body["sessions_active"], body["sessions_max"]) == (0, 1)


def test_network_endpoint_is_gzipped_json(client):
    r = client.get("/api/network", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    data = r.json()  # httpx transparently decompresses
    assert data["meta"]["units"] == "m"
    assert {j["control"] for j in data["junctions"]} == {"signalised", "give_way"}
    assert len(gzip.compress(r.content)) < len(r.content)


def test_ws_hello_then_ticks_advance_one_step_per_frame(client):
    with client.websocket_connect("/ws/sim") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["dt"] == 0.1
        ticks = [_next_tick(ws) for _ in range(5)]
        ns = [t["tick"] for t in ticks]
        assert ns == list(range(ns[0], ns[0] + 5))
        for t in ticks:
            assert t["t"] == t["tick"] / 10
            assert t["speed"] == 1 and t["step_ms"] >= 0


def test_ws_speed_control_and_pause(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "set_speed", "speed": 5}))
        while _next_tick(ws)["speed"] != 5:
            pass
        a, b = _next_tick(ws), _next_tick(ws)
        assert b["tick"] - a["tick"] == 5
        ws.send_text(json.dumps({"type": "set_speed", "speed": 0}))
        while _next_tick(ws)["speed"] != 0:
            pass
        a, b = _next_tick(ws), _next_tick(ws)
        assert a["tick"] == b["tick"]


def test_ws_reset_ping_and_invalid_messages(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "set_speed", "speed": 10}))
        for _ in range(5):
            _next_tick(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 0}))
        ws.send_text(json.dumps({"type": "reset", "seed": 7}))
        ws.send_text(json.dumps({"type": "ping", "id": 99}))
        ws.send_text(json.dumps({"type": "set_speed", "speed": 3}))  # not an allowed speed
        seen = {}
        while not {"pong", "error"} <= set(seen):
            msg = ws.receive_json()
            seen.setdefault(msg["type"], msg)
        assert seen["pong"]["id"] == 99
        assert _next_tick(ws)["tick"] < 5  # reset back to the start, still paused


def test_session_cap_rejects_with_busy_and_1013(client):
    with client.websocket_connect("/ws/sim") as first:
        first.receive_json()
        assert client.get("/api/health").json()["sessions_active"] == 1
        with client.websocket_connect("/ws/sim") as second:
            msg = second.receive_json()
            assert msg["type"] == "busy" and "busy" in msg["message"].lower()
            with pytest.raises(WebSocketDisconnect) as exc:
                second.receive_json()
            assert exc.value.code == BUSY_CLOSE_CODE
        assert client.get("/api/health").json()["sessions_rejected_total"] == 1


def test_slot_is_released_after_disconnect(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
    with client.websocket_connect("/ws/sim") as ws:  # would be busy if not released
        assert ws.receive_json()["type"] == "hello"
