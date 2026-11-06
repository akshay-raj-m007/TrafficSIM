"""Sim time must track wall time × speed, at any frame rate.

Two layers: the exact step arithmetic (``StepPacer``), and an end-to-end measurement
over a real WebSocket that prints the measured sim/wall ratios.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from trafficsim.server.app import create_app
from trafficsim.server.config import Settings
from trafficsim.server.pacing import StepPacer

WINDOW_S = 3.0  # wall-clock measurement window per case
# Frames arrive in whole 100 ms steps and are timestamped on receipt, so the ratio of a
# 3 s window resolves to about one frame (3 %) plus scheduling jitter: ±7 % is what the
# test can honestly distinguish (the exact arithmetic is covered by StepPacer's tests).
TOLERANCE = 0.07


@pytest.mark.parametrize(
    ("hz", "speed", "frames", "expected_steps"),
    [
        (10, 1, 100, 100),  # 1 step per frame
        (5, 1, 100, 200),  # 2 steps per frame
        (4, 1, 100, 250),  # alternating 2, 3
        (20, 1, 100, 50),  # every other frame
        (10, 10, 30, 300),
        (3, 1, 300, 1000),  # 10/3 steps per frame: exact over 300 frames
        (10, 0, 50, 0),
    ],
)
def test_step_counts_are_exact(hz, speed, frames, expected_steps):
    p = StepPacer(hz)
    assert sum(p.steps_for_frame(speed) for _ in range(frames)) == expected_steps


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        StepPacer(0)
    with pytest.raises(ValueError):
        StepPacer(10).steps_for_frame(-1)


@pytest.mark.parametrize(("hz", "speed"), [(10.0, 1), (10.0, 2), (5.0, 1), (20.0, 1)])
def test_sim_time_tracks_wall_time(hz, speed):
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=hz))
    with TestClient(app) as client, client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()  # hello
        ws.send_text(json.dumps({"type": "set_speed", "speed": speed}))
        first = None
        while True:
            m = ws.receive_json()
            if m["type"] != "tick" or m["speed"] != speed:
                continue
            now = time.perf_counter()
            if first is None:
                first = (now, m["t"])
            elif now - first[0] >= WINDOW_S:
                break
        wall, sim = now - first[0], m["t"] - first[1]
        ratio = sim / wall
        print(f"\n[pacing] {hz:>4} Hz, {speed}x: sim {sim:.2f} s / wall {wall:.3f} s = {ratio:.4f}")
        assert ratio == pytest.approx(speed, rel=TOLERANCE)
