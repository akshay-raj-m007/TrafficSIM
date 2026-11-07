"""Run the built-in experiments and write the shipped results (and report their cost).

    cd backend && .venv/Scripts/python tools/gen_experiments.py [--cost]

Runs every comparison of ``server/experiments.py`` (10 paired runs, 900 s, warm-up 300 s)
in a process pool and writes ``trafficsim/data/experiments/<id>.json``. Finished runs are
cached in ``backend/.cache/compare``, so the second experiment reuses the rush-hour Webster
runs of the first. ``--cost`` also measures a default-demand comparison (not shipped).
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.server import experiments as ex  # noqa: E402
from trafficsim.server.compare_jobs import CompareManager, RunCache  # noqa: E402
from trafficsim.server.compare_spec import CompareLimits  # noqa: E402
from trafficsim.server.presets_doc import preset  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "compare"
os.environ.setdefault("TRAFFICSIM_TABLE_CACHE", str(CACHE.parent / "tables"))


def run_comparison(manager: CompareManager, a: dict, b: dict, label: str) -> dict:
    job = manager.submit(ex.request_for(a, b))
    last = -1
    while job.state == "running":
        if job.done != last:
            last = job.done
            print(f"  {label}: {job.done}/{job.total} runs ({job.cached} cached)", flush=True)
        time.sleep(2.0)
    if job.state != "done":
        raise RuntimeError(f"{label}: {job.state} {job.error}")
    return job.result


def main() -> None:
    manager = CompareManager(CompareLimits(max_jobs=1), RunCache(CACHE))
    ex.DATA_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, d in ex.definitions().items():
        t0 = time.perf_counter()
        comps, runs = [], {}
        for label, a, b in d["comparisons"]:
            res = run_comparison(manager, a, b, label)
            comps.append({"label": label, "result": res})
        for c in comps:
            for side in "ab":
                for r in c["result"]["runs"][side]:
                    runs[r["key"]] = manager.cache.get(r["key"])
        doc = {"id": exp_id, "title": d["title"], "description": d["description"],
               "stamp": ex.current_stamp(), "comparisons": comps, "runs": runs}  # fmt: skip
        (ex.DATA_DIR / f"{exp_id}.json").write_text(json.dumps(doc), encoding="utf-8")
        cpu = sum(c["result"]["meta"]["cost"]["cpu_s"] for c in comps)
        print(f"{exp_id}: {len(comps)} comparison(s) in {time.perf_counter() - t0:.0f} s wall, "
              f"{cpu:.0f} CPU s computed")  # fmt: skip
    if "--cost" in sys.argv:
        a, b = preset("default"), preset("flyover_closed")
        res = run_comparison(manager, a, b, "cost: default demand")
        print("default-demand 10-run, 900 s comparison (20 runs):", res["meta"]["cost"])
    manager.shutdown()


if __name__ == "__main__":
    main()
