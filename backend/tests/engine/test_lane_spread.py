"""Vehicles spread over all lanes of a plain road, with a mild keep-left preference.

Lane shares are the occupancy (vehicles on the lane, sampled every 0.5 s) of the middle part of
a 3 km road, away from the insertion and removal ends. At light flow (300 veh/h per lane) every
lane must carry at least ``MIN_SHARE`` of the vehicles, and the kerb lane (index 0, left-hand
traffic) must still be the busiest: the bias is mild, not absent. With the old bias of
0.2 m/s^2 the median lane of 4 held only 5 % at 1,200 veh/h. The opposite bound (a car returns
to the kerb lane after overtaking) is tests/engine/test_lane_changes.py.
"""

import numpy as np
import pytest

from tests.helpers import straight_network
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import OdFlow, Scenario

MIN_SHARE = 0.15  # fixed before the run; equal sharing would be 1 / lanes
FLOW_PER_LANE_VEH_H = 300
SECONDS, WARMUP_TICKS, SAMPLE_EVERY = 500.0, 2000, 5


def lane_shares(lanes: int, seed: int = 3) -> np.ndarray:
    net = straight_network(length_m=3000.0, lanes=lanes, width_m=3.5, speed_kmh=60.0)
    demand = (OdFlow("A", "B", FLOW_PER_LANE_VEH_H * lanes),)
    sim = Simulation(
        net, Scenario(seed=seed, duration_s=SECONDS, demand=demand, signal_control="uncontrolled")
    )
    occ = np.zeros(lanes)
    while sim.step():
        vs = sim.vehicles
        if sim.tick > WARMUP_TICKS and vs.n and sim.tick % SAMPLE_EVERY == 0:
            mid = (vs.s > 1000.0) & (vs.s < 2200.0)
            occ += np.bincount(sim.lg.lane_index[vs.seg[mid]], minlength=lanes)
    return occ / occ.sum()


@pytest.mark.slow
@pytest.mark.parametrize("lanes", [2, 3, 4])
def test_all_lanes_are_used_and_the_kerb_lane_is_busiest(lanes):
    share = lane_shares(lanes)
    print(f"\n[lane spread] {lanes} lanes, kerb to median: {np.round(share, 2)}")
    assert share.min() >= MIN_SHARE
    assert int(np.argmax(share)) == 0
