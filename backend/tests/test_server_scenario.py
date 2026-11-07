"""Live changes, presets, export and import over the WebSocket."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.ws_util import hello_and_format, next_frame, next_json
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings
from trafficsim.server.presets_doc import preset

BAD_ROW = {"origin": "W", "destination": "E", "veh_per_h": -3}
WS = "/ws/sim"  # fixed-time signals: the calibration comes from the committed table


@pytest.fixture
def client():
    app = create_app(Settings(max_sessions=2, static_dir=None, tick_hz=50.0, warm_up=False))
    with TestClient(app) as c:
        yield c


def _send(ws, **msg):
    ws.send_text(json.dumps(msg))


def test_hello_carries_the_scenario_document_and_the_network_key(client):
    with client.websocket_connect(WS) as ws:
        hello, _ = hello_and_format(ws)
        assert hello["scenario"]["version"] == 1 and hello["scenario"]["changes"] == []
        assert hello["network"] == {"j2_minor_lanes": 2}
        n2 = {(r["origin"], r["destination"]): r["veh_per_h"]
              for r in hello["scenario"]["initial"]["demand"]}  # fmt: skip
        assert n2[("N2", "W")] == 37 and n2[("N2", "E")] == 214


def test_presets_and_validation_endpoints(client):
    presets = client.get("/api/presets").json()
    assert set(presets) == {"default", "rush_hour", "flyover_closed", "j2_before"}
    assert presets["j2_before"]["scenario"]["structure"]["j2_minor_lanes"] == 1
    assert client.post("/api/scenario/validate", json=preset("rush_hour")).json()["valid"]
    bad = preset("default")
    bad["initial"]["mix"]["car"] = 0
    r = client.post("/api/scenario/validate", json=bad).json()
    assert not r["valid"] and "must be exactly 100" in r["errors"][0]["message"]
    assert client.get("/api/network?j2_minor_lanes=1").status_code == 200
    assert client.get("/api/network?j2_minor_lanes=3").status_code == 422


def test_a_live_change_is_applied_logged_and_exported(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        _send(ws, type="set_speed", speed=0)
        _send(ws, type="apply", change={"type": "set_flyover", "open": False})
        ok = next_json(ws, "applied")
        t = ok["tick"]
        assert t < 20 and ok["change"] == {"tick": t, "type": "set_flyover", "open": False}
        _send(ws, type="apply", change={"type": "set_policy", "policy": "max_pressure"})
        assert next_json(ws, "applied")["change"]["policy"] == "max_pressure"
        _send(ws, type="export")
        doc = next_json(ws, "scenario")["scenario"]
        assert [c["type"] for c in doc["changes"]] == ["set_flyover", "set_policy"]


def test_invalid_changes_are_rejected_with_paths_and_change_nothing(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        cases = [
            ({"type": "set_mix", "mix": {"car": 50, "truck_bus": 10, "two_wheeler": 30, "cav": 7}},
             "mix", "shares sum to 97, must be exactly 100"),
            ({"type": "set_flyover", "open": True}, "change", "already open"),
            ({"type": "set_policy", "policy": "magic"}, "policy", "Input should be"),
            ({"type": "set_demand", "demand": [BAD_ROW]},
             "demand.0.veh_per_h", "greater than or equal to 0"),
            ({"type": "nonsense"}, "change", "does not match any of the expected tags"),
        ]  # fmt: skip
        for change, path, text in cases:
            _send(ws, type="apply", change=change)
            r = next_json(ws, "rejected")
            assert r["request"] == "apply"
            assert any(e["path"].endswith(path) and text in e["message"] for e in r["errors"]), r
        _send(ws, type="export")
        assert next_json(ws, "scenario")["scenario"]["changes"] == []  # nothing was applied


def test_reset_with_a_preset_a_seed_and_a_document(client):
    with client.websocket_connect(WS) as ws:
        _, fmt = hello_and_format(ws)
        _send(ws, type="reset", preset="j2_before", seed=5)
        h = next_json(ws, "hello")
        assert h["network"] == {"j2_minor_lanes": 1} and h["seed"] == 5 and h["epoch"] == 1
        _send(ws, type="reset", seed=9)  # same settings, new seed
        h = next_json(ws, "hello")
        assert h["seed"] == 9 and h["network"] == {"j2_minor_lanes": 1}
        doc = preset("rush_hour")
        doc["seed"] = 11
        doc["changes"] = [{"tick": 20, "type": "set_flyover", "open": False}]
        _send(ws, type="reset", scenario=doc)
        h = next_json(ws, "hello")
        assert h["seed"] == 11 and h["scenario"]["changes"] == doc["changes"]
        assert h["network"] == {"j2_minor_lanes": 2}
        assert next_frame(ws)  # the stream continues on the new epoch


def test_an_invalid_import_is_rejected_and_the_session_keeps_running(client):
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        doc = preset("default")
        doc["initial"]["mix"]["car"] = 10
        doc["structure"]["j2_minor_lanes"] = 3
        _send(ws, type="reset", scenario=doc)
        r = next_json(ws, "rejected")
        paths = {e["path"] for e in r["errors"]}
        assert r["request"] == "reset" and {"initial.mix", "structure.j2_minor_lanes"} <= paths
        _send(ws, type="reset", preset="nope")
        assert "unknown preset" in next_json(ws, "rejected")["errors"][0]["message"]
        _send(ws, type="ping", id=1)
        assert next_json(ws, "pong")["id"] == 1


def test_export_then_import_round_trips_the_document(client):
    """Import of an export gives the same document back (the engine replay of a document
    is tested exactly in tests/engine/test_live_changes.py)."""
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        _send(ws, type="set_speed", speed=0)  # paused: changes apply at tick 0, not "whenever"
        _send(ws, type="reset", scenario={**preset("rush_hour"), "seed": 3, "duration_s": 600.0})
        next_json(ws, "hello")
        _send(ws, type="apply", change={"type": "set_flyover", "open": False})
        next_json(ws, "applied")
        _send(ws, type="apply", change={"type": "set_policy", "policy": "max_pressure_threshold"})
        next_json(ws, "applied")
        _send(ws, type="export")
        doc = next_json(ws, "scenario")["scenario"]
        assert [c["tick"] for c in doc["changes"]] == [0, 0] and doc["seed"] == 3
        _send(ws, type="reset", scenario=doc)
        hello = next_json(ws, "hello")
        assert hello["scenario"] == doc  # the replayed log is the log
        _send(ws, type="export")
        assert next_json(ws, "scenario")["scenario"] == doc


def test_a_seed_only_reset_keeps_the_live_edits_like_the_panel_reset(client):
    """Header and panel resets are the same: live edits become the new initial settings."""
    with client.websocket_connect(WS) as ws:
        hello_and_format(ws)
        _send(ws, type="set_speed", speed=0)
        _send(ws, type="apply", change={"type": "set_flyover", "open": False})
        next_json(ws, "applied")
        _send(ws, type="apply", change={"type": "set_policy", "policy": "max_pressure"})
        next_json(ws, "applied")
        mix = {"car": 20, "truck_bus": 40, "two_wheeler": 30, "cav": 10}
        _send(ws, type="apply", change={"type": "set_mix", "mix": mix})
        next_json(ws, "applied")
        _send(ws, type="reset", seed=77)  # what the header button sends for a seed-only reset
        h = next_json(ws, "hello")
        doc = h["scenario"]
        assert doc["seed"] == 77 and doc["changes"] == []  # new log
        assert (
            doc["initial"]["flyover_open"] is False and doc["initial"]["policy"] == "max_pressure"
        )
        assert doc["initial"]["mix"] == mix
