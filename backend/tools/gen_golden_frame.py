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

from trafficsim.engine.lanegraph import compile_network  # noqa: E402
from trafficsim.engine.pose import PoseTable  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402
from trafficsim.network.serialize import network_to_dict  # noqa: E402
from trafficsim.server.frames import (  # noqa: E402
    FrameFormat,
    pack_frame,
    segment_table,
    unpack_frame,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "fixtures"
FMT = FrameFormat()


def golden() -> tuple[bytes, dict]:
    data = pack_frame(
        FMT, phase=2, state=1, epoch=7, tick=123456, speed_index=3,
        vid=[3, 65537, 40000, 12, 999],
        seg=[0, 5, 65535, 17, 40],
        s=[0.0, 12.345, 549.99, 3.5, 700.0],  # last one clamps to 655.35
        lat=[0.0, -1.75, 1.75, 0.07, 9.0],  # last one clamps to +6.35
        speed=[0.0, 13.9, 16.7, 25.4, 30.0],  # last one clamps to 25.5
        brake=[1, 0, 1, 0, 0],
        cls=[0, 1, 2, 3, 0],
    )  # fmt: skip
    d = unpack_frame(FMT, data)
    expected = {
        "header": {k: d[k] for k in ("phase", "state", "epoch", "tick", "n", "speed_index")},
        "vehicles": {
            k: [round(float(v), 6) for v in d[k]] for k in ("id", "seg", "s", "lat", "speed", "cls")
        }
        | {"brake": [bool(b) for b in d["brake"]]},
    }
    return data, expected


def placement() -> dict:
    """Network + segment table + server-side poses of probe points (TypeScript parity test)."""
    net = build_demo_network()
    lg = compile_network(net)
    pose = PoseTable(net, lg)
    rng = np.random.default_rng(3)
    seg = rng.integers(0, lg.n, 400)
    s = rng.uniform(0.0, 1.0, 400) * lg.length[seg]
    lat = np.where(rng.random(400) < 0.3, rng.uniform(-3.0, 3.0, 400), 0.0)
    x, y, z, h, p = pose.at(seg, s)
    probes = [
        {"seg": int(a), "s": round(float(b), 4), "lat": round(float(c), 4), "pose": [
            round(float(v), 4) for v in (px - c * np.sin(ph), py + c * np.cos(ph), pz, ph, pp)]}
        for a, b, c, px, py, pz, ph, pp in zip(seg, s, lat, x, y, z, h, p, strict=True)
    ]  # fmt: skip
    return {"network": network_to_dict(net), "segments": segment_table(lg), "probes": probes}


if __name__ == "__main__":
    data, expected = golden()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "golden_frame.bin").write_bytes(data)
    doc = {"format": FMT.to_dict(), "expected": expected}
    (FIXTURE_DIR / "golden_frame.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8"
    )
    (FIXTURE_DIR / "placement.json").write_text(json.dumps(placement()) + "\n", encoding="utf-8")
    print(f"wrote {len(data)} bytes to {FIXTURE_DIR}")
