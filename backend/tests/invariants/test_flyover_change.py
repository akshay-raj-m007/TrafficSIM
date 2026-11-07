"""Invariants hold through a live flyover close and reopen at rush-hour demand.

Same per-step checks as the other invariant tests (independent collision check, conflict
points, conservation), over a run where the flyover closes at 300 s and reopens at 600 s.
"""

import pytest

from tests.invariants.harness import run_checked
from trafficsim.engine.presets import DEMO_DEMAND, scaled
from trafficsim.engine.scenario import Scenario, SetFlyover

pytestmark = pytest.mark.slow


def test_close_and_reopen_keep_every_invariant(net):
    sc = Scenario(
        seed=42,
        duration_s=900.0,
        demand=scaled(DEMO_DEMAND, 1.5),
        changes=((3000, SetFlyover(False)), (6000, SetFlyover(True))),
    )
    rep = run_checked(net, sc, 9000)
    sim = rep.sim
    print(f"\n[flyover change] peak {rep.peak_vehicles} vehicles, min gap {rep.min_gap:.3f} m, "
          f"min speed {rep.min_speed:.3f} m/s, conflict overlaps {len(rep.conflict_overlaps)}, "
          f"rerouted {sim.rerouted}, grandfathered {len(sim.grandfathered_vids)}, "
          f"emergency brakings {sim.emergency_brakings}, box-held {sim.box_stopped_vehicle_s} "
          f"veh-s")  # fmt: skip
    assert [t for t, _ in sim.change_log] == [3000, 6000]
    assert rep.min_gap > 0.0 and rep.min_speed >= 0.0
    assert not rep.conflict_overlaps and not rep.conservation_errors
    assert sim.emergency_brakings == 0 and sim.box_stopped_vehicle_s == 0.0
    assert sim.rerouted > 50
