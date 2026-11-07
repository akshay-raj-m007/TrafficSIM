"""The lane-flow meter counts a vehicle once per segment it arrives on, lane changes included."""

import numpy as np

from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX


def test_a_lone_vehicle_is_counted_once_on_every_segment_it_visits(net):
    sim = Simulation(
        net, Scenario(seed=1, duration_s=120.0, demand=(), signal_control="uncontrolled")
    )
    lg, rt = sim.lg, sim.routes
    route = rt.add(net, lg, "W", "N2")  # starts in the wrong lane, so it changes lane once
    seg = lg.seg_of["eb_e2:1"]
    vid = sim.demand.place(
        sim.vehicles, route, CLASS_INDEX["car"], seg, float(lg.length[seg]) - 0.8, 0.0, 0.0,
        rt.roads[route].index("eb_e2"),
    )  # fmt: skip
    visited = {int(seg)}
    for _ in range(590):  # 59 s: the 5 min window is not yet full
        sim.step()
        i = sim.row_of(vid)
        if i is not None:
            visited.add(int(sim.vehicles.seg[i]))
    flow = sim.kpi_snapshot()["lane_flow"]
    assert len(flow) == lg.n
    assert visited >= {seg, lg.seg_of["eb_e2:0"]}  # it did change lane
    span = sim.time_s  # window younger than 5 min: scaled by the elapsed time
    for k in range(lg.n):
        expected = round(3600.0 / span) if k in visited else 0
        assert flow[k] == expected, lg.ids[k]
    assert np.sum(flow) == len(visited) * round(3600.0 / span)


def test_arrivals_leave_the_window_after_five_minutes(net):
    sim = Simulation(
        net, Scenario(seed=1, duration_s=500.0, demand=(), signal_control="uncontrolled")
    )
    lg, rt = sim.lg, sim.routes
    route = rt.add(net, lg, "W", "E")
    seg = lg.seg_of["eb_e2:0"]
    sim.demand.place(
        sim.vehicles, route, CLASS_INDEX["car"], seg, 10.0, 10.0, 0.0,
        rt.roads[route].index("eb_e2"),
    )  # fmt: skip
    sim.run_until(30.0)
    assert sim.kpi_snapshot()["lane_flow"][seg] == 120  # 1 arrival in 30 s
    sim.run_until(400.0)
    assert sim.kpi_snapshot()["lane_flow"][seg] == 0  # long gone from the window
