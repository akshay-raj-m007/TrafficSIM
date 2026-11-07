"""The vehicle inspector message (server/inspector.py) against direct engine state."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.ws_util import hello_and_format, next_json
from trafficsim.engine.loop import Simulation
from trafficsim.engine.params import driving
from trafficsim.engine.presets import DEMO_KPI_LAYOUT
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import VEHICLE_CLASSES
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings
from trafficsim.server.inspector import ID_MASK, Inspector


def _sim(net):
    sc = Scenario(seed=1, duration_s=400.0, demand=(), signal_control="uncontrolled")
    return Simulation(net, sc, DEMO_KPI_LAYOUT)


def test_fields_match_the_engine_state(net):
    sim = _sim(net)
    vid = sim.place_vehicle("W", "N2", "truck_bus", 1, 50.0, 8.0)  # needs a lane change at J2
    sim.run_until(30.0)
    insp = Inspector()
    insp.select(vid & ID_MASK)
    m = insp.message(sim)
    i = sim.row_of(vid)
    vs, lg = sim.vehicles, sim.lg
    c = VEHICLE_CLASSES[int(vs.cls[i])]
    assert m["gone"] is False and m["vid"] == vid and m["class"] == "truck_bus"
    assert (m["origin"], m["destination"]) == ("W", "N2")
    assert m["route"] == list(sim.routes.roads[int(vs.route[i])])
    assert m["lane"] == lg.ids[int(vs.seg[i])] and m["road"] == lg.road_of[int(vs.seg[i])]
    assert m["speed_mps"] == pytest.approx(float(vs.v[i]), abs=0.005)
    assert m["acc_mps2"] == pytest.approx(float(vs.acc[i]), abs=0.005)
    want = {"length_m": c.length_m, "width_m": c.width_m, "v0_mps": c.v0_mps, "T_s": c.T_s,
            "a_mps2": c.a_mps2, "b_mps2": c.b_mps2, "s0_m": c.s0_m}  # fmt: skip
    assert m["idm"] == want
    assert m["mobil"]["keep_left_bias_mps2"] == driving.KEEP_LEFT_BIAS_MPS2
    assert m["mobil"]["politeness"] == driving.MOBIL_POLITENESS


def test_delay_so_far_is_the_kpi_definition_and_lane_changes_come_from_the_log(net):
    sim = _sim(net)
    vid = sim.place_vehicle("W", "N2", "car", 1, 50.0, 8.0)
    insp = Inspector()
    insp.select(vid & ID_MASK)
    sim.run_until(60.0)
    sim.kpis.request_reference()
    sim.kpis.delay_ref.ref.request([], background=False)
    m = insp.message(sim)
    i = sim.row_of(vid)
    pair = sim.routes.pair[int(sim.vehicles.route[i])]
    ff = sim.kpis.delay_ref.free_flow(pair, int(sim.vehicles.cls[i]))
    assert ff is not None and m["free_flow_s"] == pytest.approx(ff, abs=0.05)
    assert m["delay_s"] == pytest.approx(sim.time_s - float(sim.vehicles.t_gen[i]) - ff, abs=0.05)
    assert m["lane_changes"] == sum(e.vid == vid for e in sim.log.lane_changes) >= 1


def test_a_vehicle_that_leaves_sends_gone_once_and_the_selection_clears(net):
    sim = _sim(net)
    vid = sim.place_vehicle("W", "E", "car", 0, 520.0, 12.0)  # near the end of the 550 m entry road
    insp = Inspector()
    insp.select(vid & ID_MASK)
    seen_gone = None
    for _ in range(4000):
        sim.step()
        m = insp.message(sim)
        if m and m["gone"]:
            seen_gone = m
            break
    assert seen_gone is not None and seen_gone["t_exit"] is not None
    assert not insp.active and insp.message(sim) is None  # nothing more is sent


def test_an_unknown_id_is_reported_as_gone(net):
    sim = _sim(net)
    insp = Inspector()
    insp.select(4242)
    assert insp.message(sim)["gone"] is True


def test_the_stream_follows_the_request_over_the_websocket():
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=50.0, warm_up=False))
    with TestClient(app) as client, client.websocket_connect("/ws/sim?signal=uncontrolled") as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 10}))
        for _ in range(400):  # wait for a vehicle to exist: frames carry their ids
            kpi = next_json(ws, "kpi")
            if kpi["counts"]["active"] > 0:
                break
        ws.send_text(json.dumps({"type": "inspect", "id": 0}))  # vid 0: the first vehicle
        first = next_json(ws, "vehicle")
        assert first["id"] == 0
        ws.send_text(json.dumps({"type": "inspect", "id": None}))
        ws.send_text(json.dumps({"type": "inspect", "id": 70000}))  # out of range: rejected
        assert next_json(ws, "error")["message"] == "invalid message"
