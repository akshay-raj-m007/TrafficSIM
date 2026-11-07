"""Measure what J2's minor approach can actually serve, for the default demand.

    cd backend && .venv/Scripts/python tools/measure_j2_capacity.py

Both minor movements (left to eastbound, right to westbound) are saturated (900 veh/h
each) under the default major-road demand and J1 signals; the number of vehicles that
actually enter the junction per movement is counted after a warm-up (the major-road
stream only reaches J2 about two minutes after the start). The default scenario then
sets each minor movement to ``UTILISATION`` x its measured capacity (README, "Defaults").
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.engine.loop import Simulation  # noqa: E402
from trafficsim.engine.presets import DEMO_DEMAND  # noqa: E402
from trafficsim.engine.scenario import OdFlow, Scenario  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402

SEEDS = (1, 2, 3)
DURATION_S = 900.0
WARMUP_S = 300.0  # excluded: the minor queue builds up and the major stream arrives
SATURATED_VEH_H = 900.0
UTILISATION = 0.8  # requested by the user: the right turn runs at about 0.8 of capacity
MOVEMENTS = {"left (N2->E)": "n2_in:0>eb_out:0", "right (N2->W)": "n2_in:1>wb_e2:1"}


def measure(seed: int, minor_lanes: int = 2) -> dict[str, float]:
    demand = tuple(f for f in DEMO_DEMAND if f.origin != "N2") + (
        OdFlow("N2", "E", SATURATED_VEH_H),
        OdFlow("N2", "W", SATURATED_VEH_H),
    )
    sim = Simulation(
        build_demo_network(minor_lanes), Scenario(seed=seed, duration_s=DURATION_S, demand=demand)
    )
    sim.run_until(DURATION_S)
    out = {}
    for name, conn in MOVEMENTS.items():
        n = sum(
            1 for e in sim.log.junction_entries if sim.lg.ids[e.conn] == conn and e.t >= WARMUP_S
        )
        out[name] = n / (DURATION_S - WARMUP_S) * 3600.0
    return out


if __name__ == "__main__":
    rows = [measure(s) for s in SEEDS]
    print(f"seeds {SEEDS}, {DURATION_S:.0f} s, warm-up {WARMUP_S:.0f} s, saturated at "
          f"{SATURATED_VEH_H:.0f} veh/h per movement")  # fmt: skip
    for name in MOVEMENTS:
        v = np.array([r[name] for r in rows])
        print(f"{name:14s} served per seed {[round(x) for x in v]} veh/h, mean {v.mean():.0f} "
              f"-> default demand {UTILISATION * v.mean():.0f} veh/h (x{UTILISATION})")  # fmt: skip
