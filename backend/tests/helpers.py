"""Small synthetic networks and trajectory helpers for engine tests."""

from __future__ import annotations

import numpy as np

from trafficsim.engine.loop import Simulation
from trafficsim.network import geometry as geo
from trafficsim.network.builder import NetworkBuilder
from trafficsim.network.types import Network


def straight_network(
    length_m: float = 3000.0, lanes: int = 1, width_m: float = 3.5, speed_kmh: float = 60.0
) -> Network:
    """One straight road from zone A to zone B (entry road = exit road)."""
    b = NetworkBuilder()
    b.road("main", "surface", geo.straight(0, 0, length_m, 0), [width_m] * lanes, 0.0, speed_kmh)
    b.zone("A", "main", "main")
    b.zone("B", "main", "main")
    return b.build()


def track(sim: Simulation, vid: int, steps: int) -> dict[str, list]:
    """Step the sim and record (t, segment id, s, v, acc) of one vehicle while it exists."""
    out: dict[str, list] = {"t": [], "seg": [], "s": [], "v": [], "acc": []}
    for _ in range(steps):
        sim.step()
        i = sim.row_of(vid)
        if i is None:
            break
        out["t"].append(sim.time_s)
        out["seg"].append(sim.lg.ids[sim.vehicles.seg[i]])
        out["s"].append(float(sim.vehicles.s[i]))
        out["v"].append(float(sim.vehicles.v[i]))
        out["acc"].append(float(sim.vehicles.acc[i]))
    return out


def on_segments(tr: dict[str, list], prefix: str) -> np.ndarray:
    """Speeds recorded while the vehicle was on segments whose id starts with prefix."""
    return np.array([v for sg, v in zip(tr["seg"], tr["v"], strict=True) if sg.startswith(prefix)])
