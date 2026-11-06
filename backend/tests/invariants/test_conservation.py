"""Invariant 4 — Conservation: spawned = active + exited; blocked spawns are counted as
unserved demand, never silently dropped.

At every step: generated = active + exited + queued, inserted = active + exited, and
vehicle ids are unique. Over capacity, the entry queues hold the unserved demand.
"""

import pytest

pytestmark = pytest.mark.slow  # long simulation runs


@pytest.mark.parametrize("run", ["medium", "overload"])
def test_vehicles_are_conserved_every_step(request, run):
    rep = request.getfixturevalue(run)
    sim = rep.sim
    d = sim.demand
    t = sim.time_s
    waiting = [t - q.t_gen for z in d.zones for q in z.queue]
    print(f"\n[conservation:{run}] generated {d.generated} = active {sim.active} + exited "
          f"{sim.exited} + queued {d.queued}; unserved: {d.queued} vehicles waiting "
          f"{sum(waiting) / 3600:.2f} veh-h (longest {max(waiting, default=0):.0f} s); "
          f"queues {d.queued_by_zone()}")  # fmt: skip
    assert not rep.conservation_errors
    assert d.generated == sim.active + sim.exited + d.queued
    exit_ids = [e.vid for e in sim.log.exits]
    assert len(set(exit_ids)) == len(exit_ids)
    assert not set(exit_ids) & set(sim.vehicles.vid.tolist())
