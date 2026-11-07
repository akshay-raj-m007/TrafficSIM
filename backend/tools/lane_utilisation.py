"""Lane utilisation report: how many vehicles use every lane and connector, and why not.

    cd backend && .venv/Scripts/python tools/lane_utilisation.py [scenario ...] [--json out.json]

Scenarios: default, rush, j2_1lane, flyover_closed, narrow (1 lane at 2.5 m), s3 (3 surface
lanes), s4f3, wide (4 lanes at 4.0 m); no argument runs them all. Per road and lane:
arrivals/h by transfer + by lane change, mean occupancy, share of the road's arrivals; every
unused lane / connector is listed with its computed cause (engine/utilisation.py).
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.engine.presets import DEFAULT_DEMAND, RUSH_SCALE, scaled  # noqa: E402
from trafficsim.engine.scenario import Scenario  # noqa: E402
from trafficsim.engine.utilisation import measure  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402
from trafficsim.network.structure import Structure  # noqa: E402

DURATION_S, WARMUP_S, SEED = 1200.0, 300.0, 1


def scenarios() -> dict[str, tuple]:
    sc = lambda **kw: Scenario(seed=SEED, duration_s=DURATION_S, demand=DEFAULT_DEMAND, **kw)  # noqa: E731
    return {
        "default": (build_demo_network(), sc()),
        "rush": (build_demo_network(), Scenario(
            seed=SEED, duration_s=DURATION_S, demand=scaled(DEFAULT_DEMAND, RUSH_SCALE))),
        "j2_1lane": (build_demo_network(1), sc()),
        "flyover_closed": (build_demo_network(), sc(flyover_open=False)),
        "narrow": (build_demo_network(Structure(2, 1, 1, 2.5, 2.5)), sc()),
        "s3": (build_demo_network(Structure(2, 3, 2, 3.5, 3.5)), sc()),
        "s4f3": (build_demo_network(Structure(2, 4, 3, 3.5, 3.5)), sc()),
        "wide": (build_demo_network(Structure(2, 4, 4, 4.0, 4.0)), sc()),
    }  # fmt: skip


def print_report(name: str, rows) -> None:
    print(f"\n=== {name} (seed {SEED}, {DURATION_S:.0f} s, warm-up {WARMUP_S:.0f} s) ===")
    roads: dict[str, list] = {}
    for r in rows:
        if r.road:
            roads.setdefault(r.road, []).append(r)
    for rid, lanes in roads.items():
        cells = " | ".join(
            f"{r.id.split(':')[1]}: {r.transfer_h:5.0f}+{r.lane_change_h:4.0f}lc "
            f"{r.share:4.0%} occ {r.occupancy:5.2f}" for r in lanes
        )  # fmt: skip
        print(f"{rid:11s} {cells}")
    unused = [r for r in rows if r.cause != "used"]
    print(f"unused ({len(unused)} of {len(rows)} segments):")
    for r in unused:
        print(f"  {r.id:28s} cause: {r.cause:12s} route demand {r.demand_h:6.0f} veh/h")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if out:
        args = [a for a in args if a != out]
    table, results = scenarios(), {}
    for name in args or list(table):
        net, sc = table[name]
        rows = measure(net, sc, WARMUP_S)
        results[name] = [asdict(r) | {"arrivals_h": r.arrivals_h} for r in rows]
        print_report(name, rows)
    if out:
        Path(out).write_text(json.dumps(results, default=float, indent=1), encoding="utf-8")
