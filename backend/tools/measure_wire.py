"""Measure the REAL bytes a live session puts on the wire, with and without compression.

    cd backend && .venv/Scripts/python tools/measure_wire.py

Starts the real uvicorn server, puts a byte-counting TCP proxy between server and
client, and connects two clients at once with identical parameters (same seed, so the
frames are identical): one that negotiates permessage-deflate (what browsers do) and one
that does not. Server -> client bytes include WebSocket framing, vehicle frames, KPI and
stats messages.

Each client reaches a loaded network at 10x, measures there, then switches to 1x and
measures again. The frame rate on the wire is 10 Hz at every speed >= 1x, but at 10x
consecutive frames are a whole simulated second apart (vehicles move ~14 m between them)
and at 1x only 0.1 s, so 1x frames are far more similar and compress much better.
"""

import asyncio
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

BACKEND = Path(__file__).resolve().parents[1]
SERVER_PORT = 8791
PROXY_PORTS = {True: 8792, False: 8793}  # keyed by "compression negotiated"
MEASURE_S = 20.0
SETTLE_S = 4.0  # after the speed change, frames of the old speed are still in flight
LOAD_TIMEOUT_S = 300.0


async def _pump(reader, writer, counter):
    try:
        while data := await reader.read(65536):
            if counter is not None:
                counter[0] += len(data)
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def _start_proxy(port: int, counter: list[int]):
    async def handle(creader, cwriter):
        sreader, swriter = await asyncio.open_connection("127.0.0.1", SERVER_PORT)
        await asyncio.gather(_pump(creader, swriter, None), _pump(sreader, cwriter, counter))

    return await asyncio.start_server(handle, "127.0.0.1", port)


async def _client(compress: bool, scale: float, target: int, counter: list[int]) -> dict:
    uri = f"ws://127.0.0.1:{PROXY_PORTS[compress]}/ws/sim?demand_scale={scale}"
    out: dict = {}
    async with websockets.connect(
        uri, compression="deflate" if compress else None, max_size=None
    ) as ws:
        await ws.send(json.dumps({"type": "set_speed", "speed": 10}))
        t_end = time.monotonic() + LOAD_TIMEOUT_S
        phase, t0, c0, frames, veh = "load", 0.0, 0, 0, 0
        async for msg in ws:
            now = time.monotonic()
            if now > t_end:
                raise TimeoutError(f"never reached {target} vehicles")
            if not isinstance(msg, bytes):
                continue
            n = struct.unpack_from("<H", msg, 8)[0]
            if phase == "load" and n >= target:
                phase, t0, c0, frames, veh = "10x", now, counter[0], 0, 0
            elif phase == "settle" and now - t0 >= SETTLE_S:
                phase, t0, c0, frames, veh = "1x", now, counter[0], 0, 0
            if phase in ("10x", "1x"):
                frames += 1
                veh += n
                if now - t0 >= MEASURE_S:
                    out[phase] = {
                        "frames": frames, "vehicles": veh / frames, "wall": now - t0,
                        "bytes": counter[0] - c0,
                    }  # fmt: skip
                    if phase == "1x":
                        break
                    await ws.send(json.dumps({"type": "set_speed", "speed": 1}))
                    phase, t0 = "settle", now
    return out


def _wait_for_server() -> None:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/api/health", timeout=1)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("server did not start")


async def measure(scale: float, target: int) -> dict:
    counters = {True: [0], False: [0]}
    proxies = [await _start_proxy(PROXY_PORTS[c], counters[c]) for c in (True, False)]
    a, b = await asyncio.gather(
        _client(True, scale, target, counters[True]),
        _client(False, scale, target, counters[False]),
    )
    for p in proxies:
        p.close()
    return {True: a, False: b}


def main() -> None:
    env = {**os.environ, "STATIC_DIR": "", "SESSION_IDLE_TIMEOUT_S": "900"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "trafficsim.server.app:app", "--port",
         str(SERVER_PORT), "--workers", "1", "--log-level", "warning"],
        cwd=BACKEND, env=env,
    )  # fmt: skip
    try:
        _wait_for_server()
        print(f"{'veh':>5} {'speed':>6} {'compression':>12} {'frames':>7} {'B/frame':>9} "
              f"{'KB/s':>7} {'MB/hour':>8} {'h per 5 GB':>11}")  # fmt: skip
        for scale, target in ((1.0, 150), (2.0, 580)):
            res = asyncio.run(measure(scale, target))
            for speed in ("1x", "10x"):
                for compress in (True, False):
                    r = res[compress][speed]
                    per_s = r["bytes"] / r["wall"]
                    print(f"{r['vehicles']:5.0f} {speed:>6} "
                          f"{'deflate' if compress else 'none':>12} {r['frames']:7d} "
                          f"{r['bytes'] / r['frames']:9.0f} {per_s / 1000:7.1f} "
                          f"{per_s * 3600 / 1e6:8.0f} {5e9 / (per_s * 3600):11.0f}")  # fmt: skip
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
