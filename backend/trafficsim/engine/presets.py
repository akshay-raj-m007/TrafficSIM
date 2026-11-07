"""Named demand presets for the demo network [veh/h per origin-destination pair].

Hand-chosen to exercise every element: flyover through traffic (W<->E), turning
movements at the signalised J1 (to/from N1 and S1), the J2 give-way minor road (N2),
and merging at the lane drop. They are scenario inputs, not calibrated to a real site.
"""

from __future__ import annotations

from dataclasses import replace

from trafficsim.engine.detectors import DetectorSpec
from trafficsim.engine.kpi import KpiLayout
from trafficsim.engine.params.control import DETECTOR_MIN_END_CLEARANCE_M
from trafficsim.engine.queues import ApproachSpec
from trafficsim.engine.scenario import OdFlow

# Cross street <-> arterial trips (N1/S1 to E/W). Without them no route used the surface
# road between J1 and the merge (the flyover is the fastest way for W<->E trips), so its lanes
# stood empty under the default demand (found by tools/lane_utilisation.py). 60 veh/h per
# flow (240 veh/h in total, against 600 veh/h of N1<->S1 through traffic), chosen as a modest
# round value before looking at any KPI; checked: no jam on seeds 1-4, J1 below saturation.
CROSS_ARTERIAL_VEH_H = 60

DEMO_DEMAND: tuple[OdFlow, ...] = (
    OdFlow("W", "E", 1100), OdFlow("E", "W", 900),
    OdFlow("W", "N1", 200), OdFlow("W", "S1", 150),
    OdFlow("E", "S1", 150), OdFlow("E", "N1", 150),
    OdFlow("N1", "S1", 300), OdFlow("S1", "N1", 300),
    OdFlow("N2", "W", 100), OdFlow("N2", "E", 100),
    OdFlow("E", "N2", 80), OdFlow("W", "N2", 80),
    OdFlow("N1", "E", CROSS_ARTERIAL_VEH_H), OdFlow("S1", "E", CROSS_ARTERIAL_VEH_H),
    OdFlow("N1", "W", CROSS_ARTERIAL_VEH_H), OdFlow("S1", "W", CROSS_ARTERIAL_VEH_H),
)  # fmt: skip

# J2 minor-road demand of the default scenario, from MEASURED capacities
# (``tools/measure_j2_capacity.py``: both movements saturated under the default major-road
# demand, seeds 1-3, 900 s, first 300 s excluded): the left turn serves 288 veh/h on
# average (per seed 396, 306, 162), the right turn 18 veh/h (18, 18, 18). Each default flow
# is 0.8 x its measured capacity, so the default demo is not overloaded on average. (The left
# turn varies a lot between seeds: on the weakest seed 230 veh/h is above capacity.)
# History: 214 / 37 veh/h before the cross-street <-> arterial flows, 234 / 30 before the
# link east of J1 followed the surface lanes.
J2_MINOR_UTILISATION = 0.8
J2_MINOR_LEFT_VEH_H = 230  # N2 -> E,  0.8 x 288
J2_MINOR_RIGHT_VEH_H = 14  # N2 -> W,  0.8 x 18

DEFAULT_DEMAND: tuple[OdFlow, ...] = tuple(
    OdFlow(f.origin, f.destination, J2_MINOR_RIGHT_VEH_H)
    if (f.origin, f.destination) == ("N2", "W")
    else OdFlow(f.origin, f.destination, J2_MINOR_LEFT_VEH_H)
    if (f.origin, f.destination) == ("N2", "E")
    else f
    for f in DEMO_DEMAND
)

# "Rush hour": every flow scaled so that J1's critical flow ratio Y (from the measured
# saturation flows) is 0.85 instead of the default demand's 0.676. Y is linear in the
# flows, so the factor is 0.85 / 0.649 (tests/test_presets.py recomputes Y).
RUSH_TARGET_Y = 0.85
DEFAULT_Y = 0.676
RUSH_SCALE = round(RUSH_TARGET_Y / DEFAULT_Y, 2)


# Detector lines and queue approaches of the demo network (positions in metres along the
# road, all at least 20 m from road ends). Road ids are those of network/demo_corridor.py.
DEMO_KPI_LAYOUT = KpiLayout(
    detectors=(
        DetectorSpec("W_IN", "West entry (eastbound, 4 lanes)", "eb_w4", 250.0),
        DetectorSpec("E_IN", "East entry (westbound)", "wb_in", 250.0),
        DetectorSpec("FLY_EB", "Flyover eastbound", "eb_flyover", 270.0),
        DetectorSpec("FLY_WB", "Flyover westbound", "wb_flyover", 270.0),
        DetectorSpec("DROP_3", "Eastbound section east of the merge", "eb_e3", 225.0),
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


def layout_for(net) -> KpiLayout:
    """The demo detector / queue layout for a network. Positions are metres along the road; on
    a road shorter than the default layout assumes (a cross-street arm gets shorter when the
    J1 box grows with wider structures) the detector sits at the same clearance from the road
    end that the default one has at most, so every detector stays inside its road."""
    length = {r.id: r.length_m for r in net.roads}
    detectors = tuple(
        replace(d, s_m=min(d.s_m, length[d.road_id] - DETECTOR_MIN_END_CLEARANCE_M))
        for d in DEMO_KPI_LAYOUT.detectors
    )
    return replace(DEMO_KPI_LAYOUT, detectors=detectors)


def scaled(demand: tuple[OdFlow, ...], factor: float) -> tuple[OdFlow, ...]:
    """The same OD pattern with every flow multiplied by ``factor``."""
    return tuple(OdFlow(f.origin, f.destination, f.veh_per_h * factor) for f in demand)
