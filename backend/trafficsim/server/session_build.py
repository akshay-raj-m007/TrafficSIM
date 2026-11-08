"""Building a live simulation (network, calibration, signal design, encoder).

This can take seconds (a vehicle mix or structure without a committed table is measured), so
the session runs it in a worker thread on private objects and swaps the result in afterwards;
the event loop, and every other session, keeps running meanwhile.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from trafficsim.engine import calibration
from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import layout_for
from trafficsim.server.frames import FrameEncoder
from trafficsim.server.live_scenario import Setup

# Seconds one connector of the J1 calibration takes on this machine (measured: 0.3 s at a full
# core, 3 s on the free tier's 0.1 CPU; the hosted config sets it). Only the first guess: the
# banner follows the real progress once the first connector is done.
PREPARE_S_PER_STEP = float(os.environ.get("PREPARE_S_PER_STEP", "0.3"))


def prepare_estimate(setup: Setup) -> float | None:
    """Seconds a first-time preparation of this layout is expected to take, None if its tables
    are already known (committed, shipped in the image or cached)."""
    steps = calibration.measurement_steps(setup.network, setup.scenario.vehicle_mix)
    return round(steps * PREPARE_S_PER_STEP) if steps else None


def build_session(
    setup: Setup, on_progress: Callable[[int, int], None] | None = None
) -> tuple[Simulation, FrameEncoder]:
    calibration.progress_hook.set(on_progress)
    sim = Simulation(setup.network, setup.scenario, layout_for(setup.network))
    return sim, FrameEncoder(sim)
