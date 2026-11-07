"""Load test: N concurrent live sessions at a given speed, and when do frames get late?

    python tools/load_test.py URL N SPEED [SECONDS]     e.g. ws://127.0.0.1:8000/ws/sim 4 1 40

Opens N WebSocket sessions at once, sets the speed, reads for SECONDS (default 40) and reports,
per run: sessions accepted / rejected (busy), mean frame rate per accepted session (the server
sends 10 frames/s), the 95th percentile of the gap between two frames, and the server's own
`lag_ms` (how late a frame left against its schedule). A session is "late" when its frame rate
is under LATE_RATE_HZ or its p95 gap is over LATE_GAP_S. The first WARMUP_S seconds (the
server builds each session in a worker thread) are not counted.
"""

import asyncio
import json
import statistics
import sys
import time

import websockets

LATE_RATE_HZ = 9.0  # of 10: under this the animation visibly stutters
LATE_GAP_S = 0.25  # a frame gap over 2.5 frame periods
WARMUP_S = 10.0


async def session(url: str, speed: float, seconds: float, out: list) -> None:
    times: list[float] = []
    lags: list[float] = []
    try:
        async with websockets.connect(url, max_size=None, open_timeout=60) as ws:
            first = json.loads(await ws.recv())
            if first.get("type") == "busy":
                out.append({"busy": True})
                return
            await ws.send(json.dumps({"type": "set_speed", "speed": speed}))
            t0 = time.monotonic()
            while time.monotonic() - t0 < seconds + WARMUP_S:
                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                now = time.monotonic() - t0
                if isinstance(msg, bytes):
                    if now >= WARMUP_S:
                        times.append(now)
                else:
                    m = json.loads(msg)
                    if m.get("type") == "stats" and now >= WARMUP_S:
                        lags.append(m.get("lag_ms", 0.0))
    except Exception as exc:  # report, do not hide
        out.append({"error": repr(exc)})
        return
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    out.append({
        "rate_hz": len(times) / seconds,
        "gap_p95_s": sorted(gaps)[int(0.95 * len(gaps))] if gaps else None,
        "lag_ms_mean": statistics.fmean(lags) if lags else None,
        "lag_ms_max": max(lags) if lags else None,
    })  # fmt: skip


async def main(url: str, n: int, speed: float, seconds: float) -> None:
    out: list[dict] = []
    await asyncio.gather(*(session(url, speed, seconds, out) for _ in range(n)))
    ok = [r for r in out if "rate_hz" in r]
    busy = sum(1 for r in out if r.get("busy"))
    err = [r["error"] for r in out if "error" in r]
    late = [r for r in ok if r["rate_hz"] < LATE_RATE_HZ or (r["gap_p95_s"] or 0) > LATE_GAP_S]
    line = f"N={n} speed={speed:g}x: accepted {len(ok)}, busy {busy}, errors {len(err)}"
    if ok:
        gaps = [r["gap_p95_s"] for r in ok if r["gap_p95_s"] is not None]
        lags = [r["lag_ms_mean"] for r in ok if r["lag_ms_mean"] is not None]
        line += (f" | frame rate mean {statistics.fmean(r['rate_hz'] for r in ok):.1f} Hz "
                 f"(min {min(r['rate_hz'] for r in ok):.1f}), p95 gap {max(gaps):.2f} s, "
                 f"server lag mean {statistics.fmean(lags) if lags else 0:.0f} ms, "
                 f"late sessions {len(late)}/{len(ok)}")  # fmt: skip
    print(line, flush=True)
    for e in err[:3]:
        print("   error:", e)


if __name__ == "__main__":
    url, n, speed = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    asyncio.run(main(url, n, speed, float(sys.argv[4]) if len(sys.argv) > 4 else 40.0))
