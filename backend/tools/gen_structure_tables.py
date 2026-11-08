"""Precompute the reference tables of the structure settings and ship them.

    cd backend && .venv/Scripts/python tools/gen_structure_tables.py [--workers N] [--list]

A reset to a new lane / width structure measures two tables (saturation flows at J1 and the
free-flow times): about 90 CPU-seconds, i.e. minutes on the free tier's 0.1 CPU. This tool measures
them in advance, in parallel, for the grid below and writes them to
``trafficsim/data/structures/`` (read by ``engine/tablecache.py`` before the writable cache; the
file names carry the input digest, so tables go stale correctly and
``tests/test_structure_tables.py`` fails until they are regenerated). Only the default vehicle mix
is covered: every preset uses it.

Grid: every lane count of both groups (1-4 x 1-4) at the default widths, with both J2 minor
approaches; and every width of both groups (2.5 to 4.0 m in 0.25 m steps) at the default lane
counts. The default structure itself is covered by the committed tables.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.engine import tablecache  # noqa: E402
from trafficsim.network.structure import LANES_RANGE, Structure  # noqa: E402

WIDTHS_M = (2.5, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0)
LANES = range(LANES_RANGE[0], LANES_RANGE[1] + 1)
MANIFEST = tablecache.SHIPPED_DIR / "manifest.json"


def grid() -> list[Structure]:
    out: dict[Structure, None] = {}
    for j2 in (2, 1):
        for s, f in itertools.product(LANES, repeat=2):
            out[Structure(j2, s, f)] = None
    for ws, wf in itertools.product(WIDTHS_M, repeat=2):
        out[Structure(2, 2, 2, ws, wf)] = None
    out.pop(Structure(), None)  # the default: committed tables
    out.pop(Structure(j2_minor_lanes=1), None)
    return list(out)


def measure(st: Structure) -> tuple[Structure, float]:
    # write straight into the directory that is shipped in the image
    os.environ[tablecache.ENV_VAR] = str(tablecache.SHIPPED_DIR)
    from trafficsim.engine.calibration import DEFAULT_MIX, saturation_flows
    from trafficsim.engine.freeflow import all_keys, reference_for
    from trafficsim.engine.lanegraph import compile_network
    from trafficsim.network.demo import build_demo_network

    t0 = time.perf_counter()
    net = build_demo_network(st)
    saturation_flows(net, DEFAULT_MIX, "J1")
    reference_for(net, compile_network(net)).request(all_keys(net), background=False)
    return st, time.perf_counter() - t0


def main() -> None:
    structures = grid()
    if "--list" in sys.argv:
        print(len(structures), "structures")
        return
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6
    tablecache.SHIPPED_DIR.mkdir(parents=True, exist_ok=True)
    t0, cpu = time.perf_counter(), 0.0
    with ProcessPoolExecutor(workers) as pool:
        for i, (st, secs) in enumerate(pool.map(measure, structures), 1):
            cpu += secs
            print(f"{i:3d}/{len(structures)} {st}  {secs:5.0f} s", flush=True)
    doc = {"structures": [
        {"j2_minor_lanes": s.j2_minor_lanes, "surface_lanes": s.surface_lanes,
         "flyover_lanes": s.flyover_lanes, "surface_width_m": s.surface_width_m,
         "flyover_width_m": s.flyover_width_m} for s in structures]}  # fmt: skip
    MANIFEST.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    size = sum(p.stat().st_size for p in tablecache.SHIPPED_DIR.glob("*.json"))
    print(f"{len(structures)} structures in {time.perf_counter() - t0:.0f} s wall "
          f"({cpu:.0f} CPU s, {workers} workers); {size / 1e6:.2f} MB written")  # fmt: skip


if __name__ == "__main__":
    main()
