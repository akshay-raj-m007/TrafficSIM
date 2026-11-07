"""Building a live simulation (network, calibration, signal design, encoder).

This can take seconds (a vehicle mix or structure without a committed table is measured), so
the session runs it in a worker thread on private objects and swaps the result in afterwards;
the event loop, and every other session, keeps running meanwhile.
"""

from __future__ import annotations

from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import DEMO_KPI_LAYOUT
from trafficsim.server.frames import FrameEncoder
from trafficsim.server.live_scenario import Setup


def build_session(setup: Setup) -> tuple[Simulation, FrameEncoder]:
    sim = Simulation(setup.network, setup.scenario, DEMO_KPI_LAYOUT)
    return sim, FrameEncoder(sim)
