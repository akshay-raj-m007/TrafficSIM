"""Demand generation, class mix, entry queues and conservation under blocking."""

import numpy as np

from tests.helpers import straight_network
from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import OdFlow, Scenario
from trafficsim.engine.vehicle import CLASS_INDEX


def test_arrival_count_and_mix_match_demand():
    rate, hours = 900.0, 1.0
    sim = Simulation(
        straight_network(), Scenario(seed=3, duration_s=3600.0, demand=(OdFlow("A", "B", rate),))
    )
    sim.run_until(3600.0)
    n = sim.demand.generated
    sd = np.sqrt(rate * hours)  # Poisson
    print(f"\n[arrivals] {n} in 1 h at {rate:.0f} veh/h (expected {rate:.0f} ± {sd:.1f})")
    assert abs(n - rate * hours) < 4 * sd

    classes = [e.cls for e in sim.log.exits] + list(sim.vehicles.cls)
    for name, share in sim.scenario.vehicle_mix:
        k = sum(1 for c in classes if c == CLASS_INDEX[name])
        sd_k = np.sqrt(len(classes) * share * (1 - share))
        print(f"[mix] {name}: {k}/{len(classes)} = {k / len(classes):.3f} (target {share})")
        assert abs(k - share * len(classes)) < 4 * sd_k


def test_blocked_entry_queues_and_conserves():
    """Demand far above a single lane's capacity: the surplus waits, nothing is dropped."""
    sim = Simulation(
        straight_network(length_m=500.0),
        Scenario(seed=4, duration_s=600.0, demand=(OdFlow("A", "B", 5000.0),)),
    )
    for _ in range(6000):
        sim.step()
        d = sim.demand
        assert d.generated == sim.active + sim.exited + d.queued
        assert d.inserted == sim.active + sim.exited
    d = sim.demand
    print(f"\n[blocked entry] generated {d.generated}, inserted {d.inserted}, "
          f"exited {sim.exited}, active {sim.active}, still queued {d.queued}")  # fmt: skip
    assert d.queued > 0


def test_same_seed_same_arrivals_different_seed_different():
    def run(seed):
        sim = Simulation(
            straight_network(),
            Scenario(seed=seed, duration_s=300.0, demand=(OdFlow("A", "B", 1200),)),
        )
        sim.run_until(300.0)
        return [(e.vid, e.cls, e.t_gen) for e in sim.log.exits]

    assert run(8) == run(8)
    assert run(8) != run(9)
