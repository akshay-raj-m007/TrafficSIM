"""Regenerate the committed saturation-flow / start-up-loss table of the demo network.

    cd backend && .venv/Scripts/python tools/gen_calibration.py

Releases a standing queue on every J1 movement and measures the saturation flow and the
start-up lost time (engine/calibration.py); takes about 8 s. Run it whenever the lane
graph, vehicle classes or model constants change
(``tests/test_calibration_table.py`` tells you).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.engine.calibration import TABLE_PATH, write_table  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402

if __name__ == "__main__":
    t0 = time.perf_counter()
    write_table(build_demo_network())
    print(f"wrote {TABLE_PATH} in {time.perf_counter() - t0:.0f} s")
