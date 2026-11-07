"""Run the validation measurements and write the stored results shown in the Validation tab.

    cd backend && .venv/Scripts/python tools/gen_validation.py [--only ring_waves ...]

Writes ``trafficsim/data/validation.json`` (about 8 minutes for everything). The file carries
the source digest of the engine; ``tests/test_validation_doc.py`` fails when it is stale.
``--only`` re-measures the named items and keeps the others from the existing file.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_measure import MEASURES  # noqa: E402
from validation_static import DOCUMENTED  # noqa: E402

from trafficsim.server import validation_doc as vd  # noqa: E402


def main() -> None:
    only = sys.argv[sys.argv.index("--only") + 1 :] if "--only" in sys.argv else []
    old = {i["id"]: i for i in (vd.stored() or {}).get("items", [])}
    measured = {}
    for key, fn in MEASURES.items():
        if only and key not in only:
            continue
        t0 = time.perf_counter()
        measured[key] = fn()
        print(f"{key}: {time.perf_counter() - t0:.0f} s", flush=True)
    items = [measured.get(k) or old.get(k) for k in MEASURES]
    if any(i is None for i in items):
        raise SystemExit("some items are missing: run without --only first")
    doc = {"stamp": vd.current_stamp(), "items": [*items, *DOCUMENTED]}
    vd.PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {vd.PATH} ({len(doc['items'])} items)")


if __name__ == "__main__":
    main()
