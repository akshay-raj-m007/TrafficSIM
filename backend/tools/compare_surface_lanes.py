"""Surface road 3 lanes x 3.5 m (A) against 2 lanes x 2.75 m (B) at rush hour, old and new model.

    cd backend && .venv/Scripts/python tools/compare_surface_lanes.py

The first comparison of these two structures showed "almost no effect"; the lane utilisation
report then showed that the surface road carried only turning traffic, with its extra lane
mostly empty. This tool separates the two things that changed since then, in a 2 x 2 design
(every cell: 10 paired runs, seeds 1-10, 900 s, warm-up 300 s, rush-hour scale of its demand):

  demand  old = 12 flows, J2 minor 214 / 37 veh/h, rush x1.31
          new = + N1/S1 -> E/W at 60 veh/h each, J2 minor 234 / 30, rush x1.11
  bias    old = keep-left bias 0.2 m/s^2   new = 0.1 m/s^2 (= the MOBIL threshold)

"old / old" reproduces the first result with today's code otherwise (it includes the stop-line
fix). The bias is set inside each worker process; reference tables are measured per bias in a
separate cache directory, so no table is ever reused under the wrong bias.
Also prints the occupancy of the surface lanes of A (utilisation report, seed 1, same window).
"""

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEEDS, DURATION_S, WARMUP_S = tuple(range(1, 11)), 900.0, 300.0
OLD_DEMAND = (  # DEMO_DEMAND before the cross-street <-> arterial flows, J2 minor as measured then
    ("W", "E", 1100), ("E", "W", 900), ("W", "N1", 200), ("W", "S1", 150), ("E", "S1", 150),
    ("E", "N1", 150), ("N1", "S1", 300), ("S1", "N1", 300), ("N2", "W", 37), ("N2", "E", 214),
    ("E", "N2", 80), ("W", "N2", 80),
)  # fmt: skip
OLD_RUSH_SCALE = 1.31
ARMS = {"A": (3, 3.5), "B": (2, 2.75)}  # surface lanes, lane width [m]
CELLS = [("new", 0.1), ("old", 0.2), ("old", 0.1), ("new", 0.2)]  # (demand, bias)
SHOWN = ("mean_delay_s", "throughput_veh_h", "unfinished_veh", "j1_queue_max_m",
         "j1_queue_mean_m", "tt_p50_s")  # fmt: skip


def make_doc(demand: str, arm: str) -> dict:
    from trafficsim.server.presets_doc import preset

    d = deepcopy(preset("rush_hour"))
    lanes, width = ARMS[arm]
    d["structure"] |= {"surface_lanes": lanes, "surface_width_m": width}
    if demand == "old":
        d["initial"]["demand"] = [
            {"origin": o, "destination": t, "veh_per_h": round(v * OLD_RUSH_SCALE, 6)}
            for o, t, v in OLD_DEMAND
        ]
    return d


def setup(bias: float, doc: dict):
    os.environ["TRAFFICSIM_TABLE_CACHE"] = str(ROOT / ".cache" / f"tables_bias{bias}")
    from trafficsim.engine import mobil
    from trafficsim.network.demo import build_demo_network
    from trafficsim.server.scenario_doc import parse, to_engine

    mobil.KEEP_LEFT_BIAS_MPS2 = bias
    p = parse(doc)
    return build_demo_network(p.structure.to_network()), to_engine(p), p


def work(task: tuple) -> tuple:
    kind, demand, bias, arm, seed = task
    net, sc, _ = setup(bias, make_doc(demand, arm))
    if kind == "prepare":
        from trafficsim.engine.freeflow import all_keys, reference_for
        from trafficsim.engine.lanegraph import compile_network

        reference_for(net, compile_network(net)).request(all_keys(net), background=False)
        return task, True
    from dataclasses import replace

    sc = replace(sc, seed=seed, duration_s=DURATION_S)
    if kind == "util":
        from trafficsim.engine.utilisation import measure

        rows = measure(net, sc, WARMUP_S)
        lanes = {r.id: (round(r.arrivals_h), round(r.occupancy, 2)) for r in rows
                 if r.road == "eb_surf_w"}  # fmt: skip
        return task, lanes
    from trafficsim.engine.runmetrics import run_metrics

    return task, run_metrics(net, sc, WARMUP_S)


def main() -> None:
    from trafficsim.engine.pairedstats import paired_difference
    from trafficsim.engine.runmetrics import METRICS

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        prep = {("prepare", "new", b, a, 0) for b in (0.1, 0.2) for a in ARMS}
        list(pool.map(work, sorted(prep)))
        print(f"tables ready ({time.perf_counter() - t0:.0f} s)", flush=True)
        tasks = [("run", d, b, a, s) for d, b in CELLS for a in ARMS for s in SEEDS]
        tasks += [("util", d, b, "A", 1) for d, b in CELLS]
        got = dict(pool.map(work, tasks, chunksize=1))
    out = {}
    for d, b in CELLS:
        print(f"\n=== demand {d}, keep-left bias {b} ===")
        cell = {}
        for m in SHOWN:
            a = [got[("run", d, b, "A", s)][m] for s in SEEDS]
            bb = [got[("run", d, b, "B", s)][m] for s in SEEDS]
            r = paired_difference(a, bb)
            cell[m] = {
                k: r[k] for k in ("mean_a", "mean_b", "diff", "ci_lo", "ci_hi", "significant")
            }
            sig = "significant" if r["significant"] else "not significant"
            print(f"{METRICS[m][0]:55s} A {r['mean_a']:8.1f}  B {r['mean_b']:8.1f}  B-A "
                  f"{r['diff']:+8.1f} [{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}] {sig}")  # fmt: skip
        cell["surface_lanes_A"] = got[("util", d, b, "A", 1)]
        print("surface lanes of A (arrivals/h, mean vehicles):", cell["surface_lanes_A"])
        out[f"{d}/{b}"] = cell
    (ROOT / ".cache" / "surface_lane_comparison.json").write_text(json.dumps(out, indent=1))
    print(f"\n{time.perf_counter() - t0:.0f} s wall")


if __name__ == "__main__":
    main()
