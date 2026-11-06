"""Named demand presets for the demo network [veh/h per origin-destination pair].

Hand-chosen to exercise every element: flyover through traffic (W<->E), turning
movements at the signalised J1 (to/from N1 and S1), the J2 give-way minor road (N2),
and merging at the lane drop. They are scenario inputs, not calibrated to a real site.
"""

from __future__ import annotations

from trafficsim.engine.detectors import DetectorSpec
from trafficsim.engine.kpi import KpiLayout
from trafficsim.engine.queues import ApproachSpec
from trafficsim.engine.scenario import OdFlow

DEMO_DEMAND: tuple[OdFlow, ...] = (
    OdFlow("W", "E", 1100), OdFlow("E", "W", 900),
    OdFlow("W", "N1", 200), OdFlow("W", "S1", 150),
    OdFlow("E", "S1", 150), OdFlow("E", "N1", 150),
    OdFlow("N1", "S1", 300), OdFlow("S1", "N1", 300),
    OdFlow("N2", "W", 100), OdFlow("N2", "E", 100),
    OdFlow("E", "N2", 80), OdFlow("W", "N2", 80),
)  # fmt: skip


# Detector lines and queue approaches of the demo network (positions in metres along the
# road, all at least 20 m from road ends). Road ids are those of network/demo_corridor.py.
DEMO_KPI_LAYOUT = KpiLayout(
    detectors=(
        DetectorSpec("W_IN", "West entry (eastbound, 4 lanes)", "eb_w4", 250.0),
        DetectorSpec("E_IN", "East entry (westbound)", "wb_in", 250.0),
        DetectorSpec("FLY_EB", "Flyover eastbound", "eb_flyover", 270.0),
        DetectorSpec("FLY_WB", "Flyover westbound", "wb_flyover", 270.0),
        DetectorSpec("DROP_3", "Eastbound 3-lane section", "eb_e3", 225.0),
        DetectorSpec("J1_W", "J1 west approach", "eb_surf_w", 405.0),
        DetectorSpec("J1_E", "J1 east approach", "wb_surf_e", 405.0),
        DetectorSpec("J1_N", "J1 north approach", "n1_in", 350.0),
        DetectorSpec("J1_S", "J1 south approach", "s1_in", 350.0),
        DetectorSpec("J2_W", "J2 west approach", "eb_e2", 160.0),
        DetectorSpec("J2_E", "J2 east approach", "wb_in", 355.0),
        DetectorSpec("J2_N", "J2 minor approach", "n2_in", 350.0),
    ),
    approaches=(
        ApproachSpec("J1_W", "J1 west", "eb_surf_w"),
        ApproachSpec("J1_E", "J1 east", "wb_surf_e"),
        ApproachSpec("J1_N", "J1 north", "n1_in"),
        ApproachSpec("J1_S", "J1 south", "s1_in"),
        ApproachSpec("J2_W", "J2 west", "eb_e2"),
        ApproachSpec("J2_E", "J2 east", "wb_in"),
        ApproachSpec("J2_N", "J2 minor", "n2_in"),
    ),
)


def scaled(demand: tuple[OdFlow, ...], factor: float) -> tuple[OdFlow, ...]:
    """The same OD pattern with every flow multiplied by ``factor``."""
    return tuple(OdFlow(f.origin, f.destination, f.veh_per_h * factor) for f in demand)
