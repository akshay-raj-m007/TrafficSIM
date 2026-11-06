"""Sim time must track wall time × speed, at any frame rate.

Two layers: the exact step arithmetic (``StepPacer``), and an end-to-end measurement
over a real WebSocket (sim time read from the binary frame header) that prints the
measured sim/wall ratios.
"""

import json

import pytest
from fastapi.testclient import TestClient

from tests.ws_util import hello_and_format, timed_frames
from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.server.app import create_app
from trafficsim.server.config import Settings
from trafficsim.server.pacing import StepPacer
from trafficsim.server.protocol import ALLOWED_SPEEDS

WINDOW_S = 3.0  # wall-clock measurement window per case
# Frames arrive in whole simulation ticks and are timestamped on receipt, so the ratio of
# a 3 s window resolves to about one tick (3 %) plus scheduling jitter: ±7 % is what the
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
        (10, 0.25, 400, 100),  # one step every 4th frame
        (10, 0.5, 100, 50),
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


SLOW = pytest.mark.slow


@pytest.mark.parametrize(
    ("hz", "speed"),
    [
        (10.0, 1),
        pytest.param(10.0, 2, marks=SLOW),
        pytest.param(5.0, 1, marks=SLOW),
        pytest.param(20.0, 1, marks=SLOW),
        pytest.param(10.0, 0.5, marks=SLOW),
    ],
)
def test_sim_time_tracks_wall_time(hz, speed):
    app = create_app(Settings(max_sessions=1, static_dir=None, tick_hz=hz, warm_up=False))
    with TestClient(app) as client, client.websocket_connect("/ws/sim?signal=uncontrolled") as ws:
        _, fmt = hello_and_format(ws)
        ws.send_text(json.dumps({"type": "set_speed", "speed": speed}))
        wall, ticks = timed_frames(ws, fmt, WINDOW_S, ALLOWED_SPEEDS.index(speed))
        ratio = ticks / STEPS_PER_SECOND / wall
        print(f"\n[pacing] {hz:>4} Hz, {speed}x: sim {ticks / 10:.2f} s / wall {wall:.3f} s "
              f"= {ratio:.4f}")  # fmt: skip
        assert ratio == pytest.approx(speed, rel=TOLERANCE)
