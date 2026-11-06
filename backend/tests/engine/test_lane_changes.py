"""MOBIL lane changes, mandatory changes (diverge / turn lanes) and the merge."""

from collections import Counter

import numpy as np
import pytest

from tests.helpers import straight_network
from trafficsim.engine.loop import Simulation
from trafficsim.engine.params.driving import B_EMERGENCY_MPS2
from trafficsim.engine.scenario import OdFlow, Scenario

DEMO_DEMAND = (
    OdFlow("W", "E", 1100), OdFlow("E", "W", 900), OdFlow("W", "N1", 200),
    OdFlow("W", "S1", 150), OdFlow("E", "S1", 150), OdFlow("E", "N1", 150),
)  # fmt: skip
STUCK_S = 60.0  # a vehicle stationary this long at the end of a wrong lane = failed change


def test_overtakes_slow_truck_and_returns_to_kerb_lane():
    sim = Simulation(straight_network(length_m=4000.0, lanes=2), Scenario(duration_s=600.0))
    truck = sim.place_vehicle("A", "B", "truck_bus", 0, 300.0, 11.0)
    car = sim.place_vehicle("A", "B", "car", 0, 120.0, 11.0)
    lanes = []
    for _ in range(1500):
        sim.step()
        lanes.append(int(sim.lg.lane_index[sim.vehicles.seg[sim.row_of(car)]]))
    vs = sim.vehicles
    ahead = vs.s[sim.row_of(car)] - vs.s[sim.row_of(truck)]
    changes = [e for e in sim.log.lane_changes if e.vid == car]
    moves = [(round(e.t, 1), e.from_seg, e.to_seg) for e in changes]
    print(f"\n[overtake] car {ahead:.0f} m ahead of truck after 150 s; lane changes "
          f"{moves}; final lane {lanes[-1]}")  # fmt: skip
    assert ahead > 0
    assert len(changes) >= 2 and lanes[-1] == 0  # out to overtake, back to the kerb lane


@pytest.fixture(scope="module")
def demo_run(net):
    sim = Simulation(net, Scenario(seed=3, duration_s=900.0, demand=DEMO_DEMAND))
    still = np.zeros(0)
    worst_decel, longest_wait = 0.0, 0.0
    waited: dict[int, float] = {}
    for _ in range(9000):
        sim.step()
        vs = sim.vehicles
        worst_decel = min(worst_decel, float(vs.acc.min()) if vs.n else 0.0)
        at_wrong_end = (vs.nxt == -1) & (vs.v < 0.1)
        for vid in vs.vid[at_wrong_end]:
            waited[int(vid)] = waited.get(int(vid), 0.0) + sim.dt
        still = vs.vid[at_wrong_end]
    longest_wait = max(waited.values(), default=0.0)
    return sim, worst_decel, longest_wait, still


@pytest.mark.slow
def test_every_destination_is_reached(demo_run):
    sim, _, longest_wait, _ = demo_run
    by_od = Counter(sim.routes.od[e.route] for e in sim.log.exits)
    print(f"\n[routes] exits by OD: {dict(by_od)}; mandatory changes "
          f"{sim.mandatory_lane_changes} of {sim.lane_changes}; longest wait at a "
          f"lane end {longest_wait:.1f} s")  # fmt: skip
    assert set(by_od) == {(f.origin, f.destination) for f in DEMO_DEMAND}
    assert longest_wait < STUCK_S


@pytest.mark.slow
def test_every_lane_change_was_safe(demo_run):
    sim, worst_decel, _, _ = demo_run
    ev = sim.log.lane_changes
    lags = np.array([e.gap_lag for e in ev if np.isfinite(e.gap_lag)])
    print(f"\n[lc safety] {len(ev)} changes; min lead gap {min(e.gap_lead for e in ev):.2f} m; "
          f"min lag gap {lags.min():.2f} m; worst follower accel "
          f"{min(e.a_follower for e in ev):.2f} m/s²; worst realised decel in run "
          f"{worst_decel:.2f} m/s²; emergency brakings {sim.emergency_brakings}")  # fmt: skip
    assert all(e.gap_lead > 0 and e.gap_lag > 0 for e in ev)
    assert all(e.a_follower >= -e.b_safe - 1e-9 for e in ev)
    assert sim.emergency_brakings == 0 and worst_decel > -B_EMERGENCY_MPS2


@pytest.mark.slow
def test_merge_gap_acceptance_on_acceleration_lane(net):
    """Surface traffic (S1→E) must merge from eb_e3 lane 0 before it ends at the drop."""
    dem = (OdFlow("W", "E", 1100), OdFlow("S1", "E", 300))
    sim = Simulation(net, Scenario(seed=5, duration_s=900.0, demand=dem))
    sim.run_until(900.0)
    acc_lane, main = sim.lg.seg_of["eb_e3:0"], sim.lg.seg_of["eb_e3:1"]
    merges = [e for e in sim.log.lane_changes if e.from_seg == acc_lane and e.to_seg == main]
    lag = np.array([e.gap_lag for e in merges if np.isfinite(e.gap_lag)])
    lead = np.array([e.gap_lead for e in merges if np.isfinite(e.gap_lead)])
    n_s1 = sum(1 for e in sim.log.exits if sim.routes.od[e.route] == ("S1", "E"))
    print(f"\n[merge] {len(merges)} merges; S1->E exited {n_s1}; accepted lag gap min "
          f"{lag.min():.1f} / median {np.median(lag):.1f} m; lead gap min {lead.min():.1f} / "
          f"median {np.median(lead):.1f} m; urgent acceptances "
          f"{sum(e.b_safe > 4.0 for e in merges)}")  # fmt: skip
    assert merges and all(e.mandatory for e in merges)
    assert n_s1 > 0 and not np.any(sim.vehicles.seg[sim.vehicles.v < 0.1] == acc_lane)
