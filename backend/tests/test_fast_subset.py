"""Guard: the fast subset (``pytest -m "not slow"``) must keep covering every area.

Marking long runs as ``slow`` is only safe if each test area still has quick tests, so
nothing becomes silently untested for local runs. CI runs everything regardless.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AREAS = ("tests/engine/", "tests/invariants/", "tests/validation/", "tests/test_server.py",
         "tests/test_network_demo.py", "tests/test_rng.py", "tests/test_loop.py")  # fmt: skip


def _collect(marker_expr: str) -> list[str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", marker_expr],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [ln.replace("\\", "/") for ln in out.splitlines() if "::" in ln]


def test_fast_subset_covers_every_area():
    fast = _collect("not slow")
    missing = [a for a in AREAS if not any(t.startswith(a) for t in fast)]
    assert not missing, f"no fast tests left in: {missing}"


def test_slow_marker_is_registered_and_used():
    slow = _collect("slow")
    assert len(slow) >= 15  # the long invariant / validation / engine runs
