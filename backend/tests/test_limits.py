"""Size limits are errors that name the limit; nothing is truncated or silently dropped."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.ws_util import hello_and_format, next_json
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario, SetFlyover
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings
from trafficsim.server.presets_doc import preset
from trafficsim.server.scenario_doc import MAX_CHANGES, problems


@pytest.fixture
def client():
    app = create_app(
        Settings(
            static_dir=None,
            warm_up=False,
            tick_hz=50.0,
            max_message_bytes=2000,
            max_live_changes=3,
            max_request_bytes=3000,
        )  # fmt: skip
    )
    with TestClient(app) as c:
        yield c


def test_an_oversized_websocket_message_is_rejected_naming_the_limit(client):
    with client.websocket_connect("/ws/sim") as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "ping", "id": 1, "pad": "x" * 3000}))
        r = next_json(ws, "rejected")
        assert r["request"] == "message"
        assert "3" in r["errors"][0]["message"] and "limit is 2000" in r["errors"][0]["message"]
        ws.send_text(json.dumps({"type": "ping", "id": 2}))  # the session is still usable
        assert next_json(ws, "pong")["id"] == 2


def test_the_live_change_limit_is_enforced_with_a_message(client):
    with client.websocket_connect("/ws/sim") as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 0}))
        for k in range(3):
            ws.send_text(
                json.dumps({"type": "apply", "change": {"type": "set_flyover", "open": k % 2 == 1}})
            )
            next_json(ws, "applied")
        ws.send_text(json.dumps({"type": "apply", "change": {"type": "set_flyover", "open": True}}))
        r = next_json(ws, "rejected")
        assert r["request"] == "apply" and "limit is 3" in r["errors"][0]["message"]


def test_a_document_with_too_many_changes_fails_validation_naming_the_limit():
    doc = preset("default")
    doc["duration_s"] = 3600.0
    doc["changes"] = [
        {"tick": t, "type": "set_policy", "policy": "max_pressure"} for t in range(MAX_CHANGES + 1)
    ]
    found = problems(doc)
    assert any(p["path"] == "changes" and str(MAX_CHANGES) in p["message"] for p in found), found


def test_a_change_after_the_end_of_the_run_is_an_error(net):
    sim = Simulation(net, Scenario(duration_s=10.0))
    with pytest.raises(ValueError, match="after the end of the run"):
        sim.schedule(SetFlyover(False), tick=500)
    sim.schedule(SetFlyover(False), tick=100)  # the last tick is fine


def test_oversized_rest_bodies_get_a_413_that_names_the_limit(client):
    big = {"a": preset("default"), "b": preset("default"), "pad": "x" * 4000}
    for url in ("/api/compare", "/api/scenario/validate"):
        r = client.post(url, content=json.dumps(big), headers={"Content-Type": "application/json"})
        assert r.status_code == 413 and "limit is 3000" in r.json()["errors"][0]["message"]
    bad = client.post(
        "/api/compare", content="not json", headers={"Content-Type": "application/json"}
    )
    assert bad.status_code == 422 and "not JSON" in bad.json()["errors"][0]["message"]
    ok = client.post("/api/scenario/validate", content="{}")  # small bodies are fine
    assert ok.status_code == 200 and ok.json()["valid"] is False
