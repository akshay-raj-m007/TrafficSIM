"""Building a scenario happens off the event loop: other sessions and pings keep running."""

import json
import time
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from tests.ws_util import hello_and_format, next_frame, next_json
from trafficsim.server import ws as ws_module
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings

BUILD_S = 2.0
SLOW_SEED = 99


@pytest.fixture
def client(monkeypatch):
    real = ws_module.build_session

    def slow(setup):  # a build that takes BUILD_S for the slow seed (like an unmeasured mix)
        if setup.scenario.seed == SLOW_SEED:
            time.sleep(BUILD_S)
        return real(setup)

    monkeypatch.setattr(ws_module, "build_session", slow)
    app = create_app(Settings(max_sessions=2, static_dir=None, tick_hz=50.0, warm_up=False))
    with TestClient(app) as c:
        yield c


def _send(ws, **msg):
    ws.send_text(json.dumps(msg))


def test_a_slow_build_neither_freezes_other_sessions_nor_answers_late(client):
    with client.websocket_connect("/ws/sim") as a, client.websocket_connect("/ws/sim") as b:
        hello_and_format(a)
        hello_and_format(b)
        _send(b, type="set_speed", speed=10)
        _send(a, type="reset", preset="default", seed=SLOW_SEED)
        t0 = time.time()
        building = next_json(a, "building")
        assert building["reason"] == "resetting" and time.time() - t0 < 1.0
        frames = [next_frame(b) for _ in range(15)]  # session B keeps streaming
        assert len(frames) == 15 and time.time() - t0 < BUILD_S - 0.3
        _send(a, type="ping", id=5)  # session A itself still answers while building
        assert next_json(a, "pong")["id"] == 5 and time.time() - t0 < BUILD_S - 0.3
        _send(a, type="apply", change={"type": "set_flyover", "open": False})
        rej = next_json(a, "rejected")
        assert rej["request"] == "apply" and "still building" in rej["errors"][0]["message"]
        _send(a, type="reset", seed=1)  # a second build while one runs is refused
        assert "still building" in next_json(a, "rejected")["errors"][0]["message"]
        hello = next_json(a, "hello")
        assert time.time() - t0 >= BUILD_S - 0.1 and hello["seed"] == SLOW_SEED
        assert hello["epoch"] == 1
        print(f"\n[build] B streamed {len(frames)} frames and A answered a ping while A "
              f"built for {BUILD_S} s")  # fmt: skip


def test_a_failing_build_keeps_the_old_simulation_running(client, monkeypatch):
    with client.websocket_connect("/ws/sim") as ws:
        hello_and_format(ws)
        monkeypatch.setattr(
            ws_module, "build_session", lambda s: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        _send(ws, type="reset", seed=5)
        err = next_json(ws, "error")
        assert "could not build the scenario" in err["message"] and "boom" in err["message"]
        _send(ws, type="ping", id=1)
        assert next_json(ws, "pong")["id"] == 1  # still alive, old simulation intact


@pytest.mark.slow  # each structure measures its saturation flows (about 8 s)
def test_the_extreme_structures_build_a_complete_live_session():
    """Setup -> simulation with the KPI layout (detectors fit every road) and encoder."""
    from trafficsim.network.structure import Structure
    from trafficsim.server import live_scenario
    from trafficsim.server.presets_doc import preset

    for st in (Structure(2, 1, 1, 2.5, 2.5), Structure(2, 4, 4, 4.0, 4.0)):
        doc = preset("default")
        doc["structure"] = asdict(st)
        sim, enc = ws_module.build_session(live_scenario.from_doc(doc))
        sim.step_n(20)
        assert enc.encode(0, 3) and len(sim.kpi_snapshot()["flow"]) == 12
