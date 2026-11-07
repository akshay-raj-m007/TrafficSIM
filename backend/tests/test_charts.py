"""Chart measurements (engine/charts.py): Edie sums, MFD points, corridor placement, stream."""

import base64
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.helpers import straight_network
from tests.ws_util import hello_and_format, next_json
from trafficsim.engine.charts import CELL_M, MFD_WINDOW_S
from trafficsim.engine.constants import DT
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import OdFlow, Scenario
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings


def _sim(net, flyover_open=True, demand=(), seconds=200.0):
    sc = Scenario(
        seed=1, duration_s=seconds, demand=demand, signal_control="uncontrolled",
        flyover_open=flyover_open,
    )  # fmt: skip
    return Simulation(net, sc)


def test_corridors_are_the_surface_and_the_flyover_route_of_each_direction(net):
    meter = _sim(net).kpis.charts
    keys = {c.key for c in meter.corridors}
    assert keys == {f"{d}_{k}" for d in ("eastbound", "westbound") for k in ("surface", "flyover")}
    by = {c.key: c for c in meter.corridors}
    assert (
        "eb_flyover" in by["eastbound_flyover"].roads
        and "eb_surf_w" in by["eastbound_surface"].roads
    )
    assert "eb_flyover" not in by["eastbound_surface"].roads


@pytest.mark.parametrize(
    "flyover_open, key", [(True, "eastbound_flyover"), (False, "eastbound_surface")]
)
def test_a_vehicle_traces_its_corridor_forward_from_end_to_end(net, flyover_open, key):
    sim = _sim(net, flyover_open, seconds=400.0)
    c = {c.key: c for c in sim.kpis.charts.corridors}[key]
    vid = sim.place_vehicle("W", "E", "car", 0, 10.0, 10.0)
    xs = []
    for _ in range(4000):
        sim.step()
        i = sim.row_of(vid)
        if i is None:
            break
        x0 = c.x0[sim.vehicles.seg[i]]
        assert x0 >= 0.0, sim.lg.ids[sim.vehicles.seg[i]]  # always on the corridor
        xs.append(x0 + float(sim.vehicles.s[i]))
    d = np.diff(xs)
    assert d.min() > -1.0 and d.max() < 2.5  # forward, at most v dt (a few connectors differ)
    assert xs[-1] > c.length_m - 40.0  # reached the end of the corridor


def test_edie_sums_equal_the_distance_and_time_of_the_vehicles_on_the_corridor(net):
    sim = _sim(net, demand=(OdFlow("W", "E", 1200), OdFlow("E", "W", 900)))
    meter = sim.kpis.charts
    for _ in range(90):  # the last 1 s window closes at tick 90
        sim.step()
    expect = [[0.0, 0.0] for _ in meter.corridors]
    for _ in range(5):  # the next window is still open: its sums are checkable
        sim.step()
        vs = sim.vehicles
        for k, c in enumerate(meter.corridors):
            on = c.x0[vs.seg] >= 0.0
            expect[k][0] += float((vs.v[on] * DT).sum())
            expect[k][1] += float(on.sum() * DT)
    assert any(e[1] > 0 for e in expect)  # vehicles were on the corridors
    for k in range(len(meter.corridors)):
        lo, hi = meter._base[k], meter._base[k + 1]
        assert meter._flat_dist[lo:hi].sum() == pytest.approx(expect[k][0], abs=1e-6)
        assert meter._flat_time[lo:hi].sum() == pytest.approx(expect[k][1], abs=1e-9)


def test_mfd_points_follow_edie_definitions_on_a_plain_road():
    net = straight_network(length_m=3000.0, lanes=2, width_m=3.5, speed_kmh=60.0)
    sim = Simulation(
        net,
        Scenario(seed=2, duration_s=120.0, demand=(OdFlow("A", "B", 800),),
                 signal_control="uncontrolled"),
    )  # fmt: skip
    dist = time = 0.0
    lane_m = 2 * 3000.0
    for _ in range(round(120.0 / DT)):
        sim.step()
        vs = sim.vehicles
        dist += float((vs.v * DT).sum())
        time += vs.n * DT
        if sim.tick % round(MFD_WINDOW_S / DT) == 0:
            t, k, q, fly = list(sim.kpis.charts.mfd)[-1]
            assert t == pytest.approx(sim.time_s)
            assert k == pytest.approx(time / (MFD_WINDOW_S * lane_m) * 1000.0, abs=1e-3)
            assert q == pytest.approx(dist / (MFD_WINDOW_S * lane_m) * 3600.0, abs=0.06)
            assert fly is True
            dist = time = 0.0


def test_the_flyover_state_is_recorded_per_mfd_point(net):
    sim = _sim(net, flyover_open=False, demand=(OdFlow("W", "E", 800),), seconds=30.0)
    sim.run_until(30.0)
    assert [p[3] for p in sim.kpis.charts.mfd] == [False] * 3


def test_incremental_since_returns_only_new_columns_and_points(net):
    sim = _sim(net, demand=(OdFlow("W", "E", 800),), seconds=60.0)
    seen: dict = {}
    sim.run_until(25.0)
    a = sim.kpis.charts.since(seen)
    assert a["col0"] == 0 and len(a["cols"]) == 25 and len(a["mfd"]) == 2 and len(a["queue"]) == 0
    sim.run_until(31.0)
    b = sim.kpis.charts.since(seen)
    assert b["col0"] == 25 and len(b["cols"]) == 6 and len(b["mfd"]) == 1
    cells = sum(c["cells"] for c in b["corridors"])
    assert all(len(base64.b64decode(x)) == cells for x in b["cols"])


def test_the_charts_stream_follows_the_request_over_the_websocket():
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=50.0, warm_up=False))
    with TestClient(app) as client, client.websocket_connect("/ws/sim?signal=uncontrolled") as ws:
        hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": 10}))
        ws.send_text(json.dumps({"type": "charts", "on": True}))
        first = next_json(ws, "charts")
        assert first["col0"] == 0 and first["corridors"] and first["cell_m"] == CELL_M
        second = next_json(ws, "charts")
        assert second["col0"] >= len(first["cols"])  # continues where the first one ended
