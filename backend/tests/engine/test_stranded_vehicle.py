"""A vehicle in a lane that does not lead onward must be able to leave it at the stop line.

The "no lane change within the stopping distance of a junction stop line" rule protects vehicles
that are committed to entering the junction. A vehicle on a lane with no connector for its route
cannot enter at all, so the rule must not hold it there: otherwise it blocks the lane for ever
(found as a permanent jam on J2's eastbound approach once the demand grew).
"""

import numpy as np

from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX


def _stranded(net):
    sim = Simulation(net, Scenario(seed=1, duration_s=120.0, signal_control="uncontrolled"))
    lg, rt = sim.lg, sim.routes
    route = rt.add(net, lg, "W", "N2")  # needs the left turn into N2, which only lane 0 has
    rpos = rt.roads[route].index("eb_e2")
    seg = lg.seg_of["eb_e2:1"]  # the wrong lane
    vid = sim.demand.place(
        sim.vehicles, route, CLASS_INDEX["car"], seg, float(lg.length[seg]) - 0.8, 0.0, 0.0, rpos
    )
    return sim, vid


def test_a_vehicle_in_a_dead_end_lane_at_the_stop_line_changes_lane_and_leaves(net):
    sim, vid = _stranded(net)
    lg = sim.lg
    i = sim.row_of(vid)
    assert int(sim.vehicles.off[i]) != 0  # it knows it is in the wrong lane
    left_at = None
    for _ in range(1200):
        sim.step()
        i = sim.row_of(vid)
        if i is None or lg.ids[int(sim.vehicles.seg[i])] != "eb_e2:1":
            left_at = sim.time_s
            break
    print(f"\n[stranded] left the dead-end lane after {left_at} s")
    assert left_at is not None and left_at < 30.0  # an empty neighbour lane: almost at once
    assert sim.lane_changes >= 1 and np.all(sim.vehicles.v >= 0)
    for _ in range(600):
        sim.step()
    assert sim.row_of(vid) is None or sim.vehicles.seg[sim.row_of(vid)] != lg.seg_of["eb_e2:1"]
