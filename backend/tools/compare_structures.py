"""Rush-hour comparison of two surface-road structures (an example of a custom A/B run).

    cd backend && .venv/Scripts/python tools/compare_structures.py

A = surface road 3 lanes x 3.5 m, B = surface road 2 lanes x 2.75 m, flyover group at its
default (2 lanes x 3.5 m), rush-hour demand, 10 paired runs (seeds 1-10), 900 s, warm-up 300 s.
Reference tables of the two structures are measured once in a "preparing" phase.
"""

import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "compare"
os.environ.setdefault("TRAFFICSIM_TABLE_CACHE", str(CACHE.parent / "tables"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.server.compare_jobs import CompareManager, RunCache  # noqa: E402
from trafficsim.server.compare_spec import CompareLimits  # noqa: E402
from trafficsim.server.presets_doc import preset  # noqa: E402


def doc(name: str, lanes: int, width: float) -> dict:
    d = deepcopy(preset("rush_hour"))
    d["name"] = name
    d["structure"] |= {"surface_lanes": lanes, "surface_width_m": width}
    return d


if __name__ == "__main__":
    a, b = doc("Surface 3 lanes x 3.5 m", 3, 3.5), doc("Surface 2 lanes x 2.75 m", 2, 2.75)
    manager = CompareManager(CompareLimits(max_jobs=1), RunCache(CACHE))
    job = manager.submit({"a": a, "b": b, "runs": 10, "duration_s": 900.0, "warmup_s": 300.0,
                          "base_seed": 1})  # fmt: skip
    t0, phase = time.perf_counter(), None
    while job.state == "running":
        if job.phase != phase or True:
            phase = job.phase
            print(f"  {job.phase}: {job.done}/{job.total} ({time.perf_counter() - t0:.0f} s)", flush=True)
        time.sleep(15)
    if job.state != "done":
        raise SystemExit(f"{job.state}: {job.error}")
    out = Path(__file__).resolve().parents[1] / ".cache" / "structure_comparison.json"
    out.write_text(json.dumps(job.result), encoding="utf-8")
    print("cost", job.result["meta"]["cost"])
    manager.shutdown()
