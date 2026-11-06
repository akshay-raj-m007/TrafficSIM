"""Named demand presets for the demo network [veh/h per origin-destination pair].

Hand-chosen to exercise every element: flyover through traffic (W<->E), turning
movements at the signalised J1 (to/from N1 and S1), the J2 give-way minor road (N2),
and merging at the lane drop. They are scenario inputs, not calibrated to a real site.
"""

from __future__ import annotations

from trafficsim.engine.scenario import OdFlow

DEMO_DEMAND: tuple[OdFlow, ...] = (
    OdFlow("W", "E", 1100), OdFlow("E", "W", 900),
    OdFlow("W", "N1", 200), OdFlow("W", "S1", 150),
    OdFlow("E", "S1", 150), OdFlow("E", "N1", 150),
    OdFlow("N1", "S1", 300), OdFlow("S1", "N1", 300),
    OdFlow("N2", "W", 100), OdFlow("N2", "E", 100),
    OdFlow("E", "N2", 80), OdFlow("W", "N2", 80),
)  # fmt: skip


def scaled(demand: tuple[OdFlow, ...], factor: float) -> tuple[OdFlow, ...]:
    """The same OD pattern with every flow multiplied by ``factor``."""
    return tuple(OdFlow(f.origin, f.destination, f.veh_per_h * factor) for f in demand)
