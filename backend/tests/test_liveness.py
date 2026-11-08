"""Slots are freed when a connection dies or sits idle (the hosted server showed "busy" with
one tab because dead connections kept their slot)."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.ws_util import next_json, recv
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings
from trafficsim.server.liveness import DEAD, IDLE, Liveness

WS = "/ws/sim?signal=uncontrolled"
HEARTBEAT_S = 1.5


def _client(**kw):
    s = Settings(max_sessions=2, static_dir=None, tick_hz=50.0, warm_up=False, **kw)
    return TestClient(create_app(s))


def test_liveness_clocks():
    lv = Liveness(heartbeat_s=30.0, idle_s=600.0, now=0.0)
    assert lv.verdict(29.0) is None and lv.verdict(31.0) == DEAD
    lv.heartbeat(31.0)  # a ping keeps the connection alive ...
    assert lv.verdict(40.0) is None
    for t in range(0, 700, 10):  # ... but pings alone do not count as activity
        lv.heartbeat(float(t))
    assert lv.verdict(700.0) == IDLE
    lv.activity(700.0)
    assert lv.verdict(701.0) is None


def test_a_dead_connection_frees_its_slot_and_a_third_session_can_connect():
    with _client(heartbeat_timeout_s=HEARTBEAT_S) as client:
        with client.websocket_connect(WS) as alive, client.websocket_connect(WS) as dead:
            next_json(alive, "hello")
            next_json(dead, "hello")
            assert client.get("/api/health").json()["sessions_active"] == 2
            # `dead` now goes silent without closing (no pings, no close frame); `alive` pings
            t0, third = time.monotonic(), None
            while time.monotonic() - t0 < HEARTBEAT_S + 6.0 and third is None:
                alive.send_text(json.dumps({"type": "ping", "id": 1}))
                next_json(alive, "pong")
                with client.websocket_connect(WS) as probe:
                    first = recv(probe)
                    if first["type"] != "busy":  # "building" / "hello": it got a slot
                        third = time.monotonic() - t0
                time.sleep(0.2)
            assert third is not None, "a third session never got a slot"
            assert third < HEARTBEAT_S + 4.0  # within the heartbeat timeout plus a tick or two
            h = client.get("/api/health").json()
            assert h["sessions_closed"].get("dead", 0) == 1
            assert h["session_ages_s"] and h["sessions_max"] == 2
        # the live one kept its slot the whole time
        assert client.get("/api/health").json()["sessions_active"] <= 1


def test_an_idle_session_is_paused_and_closed_with_a_message_and_its_slot_freed():
    with _client(idle_timeout_s=1.0, heartbeat_timeout_s=30.0) as client:
        with client.websocket_connect(WS) as ws:
            next_json(ws, "hello")
            t0 = time.monotonic()
            while True:  # pings only: the page is open but nobody is using it
                ws.send_text(json.dumps({"type": "ping", "id": 1}))
                msg = recv(ws)
                if isinstance(msg, dict) and msg.get("type") == "idle":
                    break
                assert time.monotonic() - t0 < 8.0, "no idle message"
                time.sleep(0.1)
            assert "Click to resume" in msg["message"]
            with pytest.raises(WebSocketDisconnect) as exc:
                while True:
                    recv(ws)
            assert exc.value.code == 4000
        h = client.get("/api/health").json()
        assert h["sessions_active"] == 0 and h["sessions_closed"].get("idle") == 1


def test_activity_messages_keep_a_session_from_going_idle():
    with _client(idle_timeout_s=1.5) as client, client.websocket_connect(WS) as ws:
        next_json(ws, "hello")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3.5:  # twice the idle timeout, with the visitor "active"
            ws.send_text(json.dumps({"type": "activity"}))
            msg = recv(ws)
            assert not (isinstance(msg, dict) and msg.get("type") == "idle")
            time.sleep(0.2)
        assert client.get("/api/health").json()["sessions_active"] == 1


def test_a_blocked_server_loop_does_not_make_a_healthy_client_dead(monkeypatch):
    """On the 0.1 CPU free tier a long build starves the event loop: the client's pings wait
    unread for longer than the heartbeat timeout. That session must not be declared dead."""
    from trafficsim.engine.loop import Simulation

    real, blocked = Simulation.step_n, []

    def slow_once(self, n):
        if not blocked and self.tick > 20:
            blocked.append(1)
            time.sleep(HEARTBEAT_S + 1.0)  # the loop is stuck for longer than the timeout
        return real(self, n)

    monkeypatch.setattr(Simulation, "step_n", slow_once)
    with _client(heartbeat_timeout_s=HEARTBEAT_S) as client, client.websocket_connect(WS) as ws:
        next_json(ws, "hello")
        ws.send_text(json.dumps({"type": "set_speed", "speed": 1}))
        t0 = time.monotonic()
        while time.monotonic() - t0 < HEARTBEAT_S + 4.0:
            ws.send_text(json.dumps({"type": "ping", "id": 1}))
            recv(ws)
            time.sleep(0.2)
        h = client.get("/api/health").json()
        assert blocked and h["sessions_active"] == 1 and h["sessions_closed"].get("dead", 0) == 0
