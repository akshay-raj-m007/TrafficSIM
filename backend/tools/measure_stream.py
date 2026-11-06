"""Measure what one live session costs to stream: frame size, bandwidth, CPU.

    cd backend && .venv/Scripts/python tools/measure_stream.py

For each demand scale the demo is run to a loaded state, then consecutive frames (one per
simulation tick, i.e. what a 1x session at 10 Hz sends) are encoded exactly as the server
does. Reported per scale: vehicles, raw frame bytes, bytes after a streaming deflate with
context takeover (what permessage-deflate sends when the browser negotiates it; the
trailing 4 bytes it strips are not counted), KPI/stats JSON per second, bandwidth, and
the wall-clock cost of a simulation step, a frame encode and a KPI snapshot.
"""

import json
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trafficsim.engine.loop import Simulation  # noqa: E402
from trafficsim.engine.presets import DEMO_KPI_LAYOUT  # noqa: E402
from trafficsim.network.demo import build_demo_network  # noqa: E402
from trafficsim.server import protocol  # noqa: E402
from trafficsim.server.frames import FrameEncoder  # noqa: E402
from trafficsim.server.session_config import SessionParams  # noqa: E402

FRAME_HZ = 10.0  # frames per wall second at speed >= 1
AUX_BYTES_PER_S_MARGIN = 0  # kpi + stats are measured, not assumed
RENDER_BUDGET_GB_PER_MONTH = 5.0  # Render free tier outbound bandwidth (decimal GB)


def measure(scale: float, warm_s: float, frames: int = 100, signal: str = "fixed_webster") -> dict:
    net = build_demo_network()
    sim = Simulation(net, SessionParams(42, signal, scale).scenario(), DEMO_KPI_LAYOUT)
    enc = FrameEncoder(sim)
    sim.run_until(warm_s)
    deflate = zlib.compressobj(level=6, wbits=-15)  # raw deflate, 32 KiB window
    raw, packed, enc_ms, step_ms, veh = [], [], [], [], []
    for _ in range(frames):
        t0 = time.perf_counter()
        sim.step()
        t1 = time.perf_counter()
        frame = enc.encode(0, 3)
        t2 = time.perf_counter()
        wire = deflate.compress(frame) + deflate.flush(zlib.Z_SYNC_FLUSH)
        raw.append(len(frame))
        packed.append(len(wire) - 4)
        step_ms.append((t1 - t0) * 1000)
        enc_ms.append((t2 - t1) * 1000)
        veh.append(sim.active)
    t3 = time.perf_counter()
    kpi_json = json.dumps(protocol.kpi(sim.kpi_snapshot()), separators=(",", ":"))
    kpi_ms = (time.perf_counter() - t3) * 1000
    stats_json = json.dumps(
        protocol.stats(sim.time_s, sim.tick, 1, False, 0.0, {"frames": 10, "frame_bytes_mean": 0,
                       "bytes_per_s": 0, "step_ms_mean": 0.0, "step_ms_max": 0.0,
                       "encode_ms_mean": 0.0, "bytes_total": 0, "frames_total": 0,
                       "vehicles": sim.active}),
        separators=(",", ":"),
    )  # fmt: skip
    n = len(raw)
    return {
        "scale": scale, "vehicles": sum(veh) / n, "raw_B": sum(raw) / n,
        "packed_B": sum(packed) / n, "aux_B_per_s": len(kpi_json) + len(stats_json),
        "step_ms": sum(step_ms) / n, "encode_ms": sum(enc_ms) / n, "kpi_ms": kpi_ms,
    }  # fmt: skip


def bandwidth(row: dict, hz: float = FRAME_HZ) -> dict:
    out = {}
    for key in ("raw_B", "packed_B"):
        bytes_s = row[key] * hz + row["aux_B_per_s"]
        out[key] = {
            "KB_per_s": bytes_s / 1000.0,
            "MB_per_hour": bytes_s * 3600 / 1e6,
            "hours_per_budget": RENDER_BUDGET_GB_PER_MONTH * 1e9 / (bytes_s * 3600),
        }
    return out


def main() -> None:
    rows = [measure(1.0, 300.0), measure(2.0, 900.0)]
    print(f"{'veh':>5} {'raw B/frame':>12} {'deflated':>9} {'kpi+stats B/s':>14} "
          f"{'step ms':>8} {'encode ms':>10} {'kpi ms':>7}")  # fmt: skip
    for r in rows:
        print(f"{r['vehicles']:5.0f} {r['raw_B']:12.0f} {r['packed_B']:9.0f} "
              f"{r['aux_B_per_s']:14d} {r['step_ms']:8.2f} {r['encode_ms']:10.3f} "
              f"{r['kpi_ms']:7.2f}")  # fmt: skip
    print(
        f"\nbandwidth per session at {FRAME_HZ:.0f} frames/s "
        f"(session-hours that fit in {RENDER_BUDGET_GB_PER_MONTH:.0f} GB/month):"
    )
    for r in rows:
        for hz in (FRAME_HZ, FRAME_HZ / 2):
            b = bandwidth(r, hz)
            for key, label in (("raw_B", "raw"), ("packed_B", "deflated")):
                x = b[key]
                print(f"  {r['vehicles']:4.0f} veh, {hz:4.1f} Hz, {label:8s}: "
                      f"{x['KB_per_s']:6.1f} KB/s = {x['MB_per_hour']:5.0f} MB/h -> "
                      f"{x['hours_per_budget']:5.0f} h")  # fmt: skip


if __name__ == "__main__":
    main()
