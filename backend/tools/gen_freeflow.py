"""Regenerate the committed free-flow travel-time table of the demo network.

    cd backend && .venv/Scripts/python tools/gen_freeflow.py

Measures one vehicle alone on the empty network for every (origin-destination route,
vehicle class), writes ``trafficsim/data/freeflow_demo.json`` with a digest of all inputs.
Takes about a minute. Run it whenever the lane graph, vehicle classes or model constants
change (``tests/test_kpi.py::test_committed_freeflow_table_is_current`` tells you).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.engine.freeflow import TABLE_PATH, TABLE_PATH_J2_1, FreeFlowReference  # noqa: E402
from trafficsim.engine.lanegraph import compile_network  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402

if __name__ == "__main__":
    for lanes, path in ((2, TABLE_PATH), (1, TABLE_PATH_J2_1)):
        net = build_demo_network(lanes)
        t0 = time.perf_counter()
        ref = FreeFlowReference(net)
        ref.write_table(compile_network(net), path)
        print(f"wrote {path} ({len(ref._values)} values) in {time.perf_counter() - t0:.0f} s")
