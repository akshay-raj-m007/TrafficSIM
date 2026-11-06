"""Invariant 2 — No collisions, no negative speeds: gap > 0 and v >= 0 at every step.

Checked independently of the engine's own leader search (tests/invariants/harness.py):
every pair of consecutive vehicle bodies on a segment (tails included) and every
conflict point inside the junctions, at every step, in a medium-demand run with
fixed-time signals and an over-capacity run with max-pressure signals.
"""

import pytest


@pytest.mark.parametrize("run", ["medium", "overload"])
def test_no_collision_and_no_negative_speed(request, run):
    rep = request.getfixturevalue(run)
    sim = rep.sim
    print(f"\n[no-collision:{run}] {len(rep.hashes)} steps, peak {rep.peak_vehicles} vehicles, "
          f"min bumper gap {rep.min_gap:.3f} m, min speed {rep.min_speed:.4f} m/s, "
          f"conflict-point overlaps {len(rep.conflict_overlaps)}, emergency brakings "
          f"{sim.emergency_brakings}, lane changes {sim.lane_changes}, "
          f"exited {sim.exited}")  # fmt: skip
    assert rep.min_gap > 0.0
    assert rep.min_speed >= 0.0
    assert not rep.conflict_overlaps
