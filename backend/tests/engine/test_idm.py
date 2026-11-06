"""IDM car-following: free road, equilibrium gap, stopping, ballistic update."""

import numpy as np
import pytest

from tests.helpers import straight_network, track
from trafficsim.engine.constants import DT
from trafficsim.engine.idm import ballistic_update, idm_accel
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX, VEHICLE_CLASSES


def _sim(**kw) -> Simulation:
    return Simulation(straight_network(**kw), Scenario(duration_s=600.0))


@pytest.mark.parametrize("cls", ["car", "truck_bus", "two_wheeler", "cav"])
def test_free_road_speed_converges_to_v0_eff(cls):
    sim = _sim(length_m=3000.0, speed_kmh=60.0)
    vid = sim.place_vehicle("A", "B", cls, 0, 10.0, 0.0)
    tr = track(sim, vid, 1500)
    v0 = sim.lg.v0_eff[0, CLASS_INDEX[cls]]
    v_end = tr["v"][-1]
    print(f"\n[free road] {cls}: v_end {v_end * 3.6:.2f} km/h vs v0_eff {v0 * 3.6:.2f} km/h")
    assert v_end == pytest.approx(v0, rel=0.01)
    assert min(tr["v"]) >= 0.0


def test_equilibrium_gap_matches_idm_theory():
    """A car behind a slower truck settles at s_e = (s0 + vT) / sqrt(1 - (v/v0)^4)."""
    sim = _sim(length_m=6000.0, speed_kmh=60.0)
    truck = sim.place_vehicle("A", "B", "truck_bus", 0, 300.0, 13.0)
    car = sim.place_vehicle("A", "B", "car", 0, 200.0, 13.0)
    sim.run_until(240.0)
    vs = sim.vehicles
    it, ic = sim.row_of(truck), sim.row_of(car)
    gap = vs.s[it] - VEHICLE_CLASSES[1].length_m - vs.s[ic]
    c = VEHICLE_CLASSES[0]
    v = vs.v[ic]
    v0 = sim.lg.v0_eff[0, 0]
    s_e = (c.s0_m + v * c.T_s) / np.sqrt(1.0 - (v / v0) ** 4)
    print(f"\n[equilibrium] v {v * 3.6:.2f} km/h, gap {gap:.3f} m, theory {s_e:.3f} m")
    assert gap == pytest.approx(s_e, rel=0.01)


def test_stops_behind_stationary_obstacle_without_collision():
    """Pure IDM kinematics: approach a standing vehicle from 50 km/h."""
    car = VEHICLE_CLASSES[0]
    s, v = np.array([0.0]), np.array([50 / 3.6])
    obstacle = 200.0
    gaps, accs = [], []
    for _ in range(int(120 / DT)):
        gap = np.array([obstacle - s[0]])
        acc = idm_accel(
            v, np.array([car.v0_mps]), np.array([car.T_s]), np.array([car.a_mps2]),
            np.array([car.b_mps2]), np.array([car.s0_m]), gap, v - 0.0,
        )  # fmt: skip
        s, v = ballistic_update(s, v, acc)
        gaps.append(obstacle - s[0])
        accs.append(acc[0])
    print(f"\n[stop] final gap {gaps[-1]:.3f} m (s0 = {car.s0_m}), min gap {min(gaps):.3f} m,"
          f" peak decel {-min(accs):.2f} m/s²")  # fmt: skip
    assert min(gaps) > 0.0
    assert gaps[-1] == pytest.approx(car.s0_m, abs=0.05)
    assert v[0] < 1e-3


def test_ballistic_update_never_goes_negative():
    s = np.array([0.0, 0.0, 0.0])
    v = np.array([0.5, 1.0, 0.0])
    acc = np.array([-9.0, -50.0, -3.0])
    s2, v2 = ballistic_update(s, v, acc)
    assert np.all(v2 >= 0.0)
    np.testing.assert_allclose(s2[:2], v[:2] ** 2 / (2 * -acc[:2]))  # exact stop distance
    assert s2[2] == 0.0
