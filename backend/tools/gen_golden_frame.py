"""Write the golden binary frame shared by the Python and TypeScript decoder tests.

    cd backend && .venv/Scripts/python tools/gen_golden_frame.py

The frame is built from fixed numbers (no simulation), so it only changes if the frame
format changes. Outputs, in ``frontend/src/api/fixtures/``: ``golden_frame.bin`` and
``golden_frame.json`` (format description + the decoded values both decoders must give).
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.server.frames import FrameFormat, pack_frame, unpack_frame  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "fixtures"
FMT = FrameFormat(x0_m=-1010.0, y0_m=-420.0)


def golden() -> tuple[bytes, dict]:
    data = pack_frame(
        FMT, phase=2, state=1, epoch=7, tick=123456, speed_index=3,
        vid=[3, 65537, 40000, 12, 999],
        x=[-1000.0, 0.0, 270.25, 1499.95, -450.5],
        y=[-9.75, 3.5, 4.5, 0.0, 12.25],
        z=[0.0, 6.5, 3.25, 0.0, 1.5],
        heading=[0.0, np.pi, np.pi / 2, 2 * np.pi - 0.001, -np.pi / 2],
        pitch=[0.0, 0.0, 0.054, -0.054, 0.2],  # last one clamps to +0.127
        speed=[0.0, 13.9, 16.7, 25.4, 30.0],  # last one clamps to 25.5
        brake=[1, 0, 1, 0, 0],
        cls=[0, 1, 2, 3, 0],
    )  # fmt: skip
    d = unpack_frame(FMT, data)
    expected = {
        "header": {k: d[k] for k in ("phase", "state", "epoch", "tick", "n", "speed_index")},
        "vehicles": {
            k: [round(float(v), 6) for v in d[k]]
            for k in ("id", "x", "y", "z", "heading", "pitch", "speed", "cls")
        }
        | {"brake": [bool(b) for b in d["brake"]]},
    }
    return data, expected


if __name__ == "__main__":
    data, expected = golden()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "golden_frame.bin").write_bytes(data)
    doc = {"format": FMT.to_dict(), "expected": expected}
    (FIXTURE_DIR / "golden_frame.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(data)} bytes to {FIXTURE_DIR}")
