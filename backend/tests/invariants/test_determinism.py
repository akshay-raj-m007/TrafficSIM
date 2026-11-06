"""Invariant 1 — Determinism: same seed and scenario give identical trajectories and KPIs.

The full vehicle state (ids, segments, positions, speeds, routes, tails) and the
conservation counters are hashed at every step and compared bit for bit.
"""

from tests.invariants.conftest import RUN_S, STEPS
from tests.invariants.harness import run_checked
from trafficsim.engine.presets import DEMO_DEMAND
from trafficsim.engine.scenario import Scenario


def _exits(rep):
    return [(e.vid, e.cls, e.route, e.t_gen, e.t_ins, e.t_exit) for e in rep.sim.log.exits]


def test_same_seed_identical_every_step(net, medium):
    again = run_checked(net, Scenario(seed=5, duration_s=RUN_S, demand=DEMO_DEMAND), STEPS)
    first_diff = next(
        (k for k, (a, b) in enumerate(zip(medium.hashes, again.hashes, strict=True)) if a != b),
        None,
    )
    print(f"\n[determinism] {len(medium.hashes)} steps compared; first difference: {first_diff}; "
          f"exits {len(_exits(medium))} vs {len(_exits(again))}; peak vehicles "
          f"{medium.peak_vehicles}")  # fmt: skip
    assert medium.hashes == again.hashes
    assert _exits(medium) == _exits(again)
    assert medium.sim.log.lane_changes == again.sim.log.lane_changes


def test_different_seed_differs(net, medium):
    other = run_checked(net, Scenario(seed=6, duration_s=60.0, demand=DEMO_DEMAND), 600)
    assert other.hashes != medium.hashes[:600]
