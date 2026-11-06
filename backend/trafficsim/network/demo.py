"""The hand-built demo network (not from OpenStreetMap).

Contains every element the brief requires:
  * J1 — 4-arm signalised junction at x=0 (cross street N1/S1, 2+2 lanes, 3.25 m);
    the flyover deck passes over it.
  * J2 — give-way T-junction at x=1100; minor road N2 (1+1 lanes, 2.75 m) yields.
  * Flyover with diverge/merge ramps; through traffic chooses it by destination.
  * Roads with 1, 2, 3 and 4 lanes; a 3→2 lane drop (bottleneck) at x=900.
  * Left / through / right turning movements at both junctions.
"""

from __future__ import annotations

from functools import lru_cache

from trafficsim.network import geometry as geo
from trafficsim.network.builder import NetworkBuilder
from trafficsim.network.demo_corridor import (
    DECK_THICKNESS,
    DECK_Z,
    J1_HALF_X,
    J1_HALF_Y,
    J2_HALF_X,
    J2_MINOR_Y,
    J2_X,
    MEDIAN_HALF,
    MIN_CLEARANCE,
    W_ART,
    X_DROP,
    X_WEST,
    add_corridor,
)

W_CROSS = 3.25  # J1 cross-street lanes
W_MINOR = 2.75  # narrow minor road at J2
ARM_LEN = 400.0  # length of the cross-street arms from the corridor centreline


def _add_cross_streets(b: NetworkBuilder) -> None:
    c2 = [W_CROSS, W_CROSS]
    # J1 cross street (x = 0). Southbound lanes sit east of the centreline (LHT).
    b.road("n1_in", "surface", geo.straight(0, ARM_LEN, 0, J1_HALF_Y), c2, 0.5, 40)
    b.road("n1_out", "surface", geo.straight(0, J1_HALF_Y, 0, ARM_LEN), c2, 0.5, 40)
    b.road("s1_in", "surface", geo.straight(0, -ARM_LEN, 0, -J1_HALF_Y), c2, 0.5, 40)
    b.road("s1_out", "surface", geo.straight(0, -J1_HALF_Y, 0, -ARM_LEN), c2, 0.5, 40)
    # J2 minor road (x = 1100), single lane each way, no median.
    b.road("n2_in", "surface", geo.straight(J2_X, ARM_LEN, J2_X, J2_MINOR_Y), [W_MINOR], 0.0, 30)
    b.road("n2_out", "surface", geo.straight(J2_X, J2_MINOR_Y, J2_X, ARM_LEN), [W_MINOR], 0.0, 30)


def _add_j1_turns(b: NetworkBuilder) -> None:
    t = b.turn
    # West arm (eastbound approach): lane 0 = left only, lane 1 = through + right.
    t("J1", "eb_surf_w", 0, "n1_out", 0, "left")
    t("J1", "eb_surf_w", 1, "eb_surf_e", 0, "through")
    t("J1", "eb_surf_w", 1, "s1_out", 1, "right")
    # East arm (westbound approach, single narrow lane).
    t("J1", "wb_surf_e", 0, "s1_out", 0, "left")
    t("J1", "wb_surf_e", 0, "wb_surf_w", 1, "through")
    t("J1", "wb_surf_e", 0, "n1_out", 1, "right")
    # North arm (southbound approach).
    t("J1", "n1_in", 0, "eb_surf_e", 0, "left")
    t("J1", "n1_in", 0, "s1_out", 0, "through")
    t("J1", "n1_in", 1, "s1_out", 1, "through")
    t("J1", "n1_in", 1, "wb_surf_w", 1, "right")
    # South arm (northbound approach).
    t("J1", "s1_in", 0, "wb_surf_w", 0, "left")
    t("J1", "s1_in", 0, "n1_out", 0, "through")
    t("J1", "s1_in", 1, "n1_out", 1, "through")
    t("J1", "s1_in", 1, "eb_surf_e", 0, "right")
    b.junction("J1", "signalised", (-J1_HALF_X, J1_HALF_X), (-J1_HALF_Y, J1_HALF_Y))


def _add_j2_turns(b: NetworkBuilder) -> None:
    t = b.turn
    major_half = MEDIAN_HALF + 2 * W_ART
    # Minor approach (southbound from N2) gives way to all major-road traffic.
    t("J2", "n2_in", 0, "eb_out", 0, "left", yields=True)
    t("J2", "n2_in", 0, "wb_e2", 1, "right", yields=True)
    # Major eastbound: through, plus a left turn into N2 (no opposing stream in LHT).
    t("J2", "eb_e2", 0, "eb_out", 0, "through")
    t("J2", "eb_e2", 1, "eb_out", 1, "through")
    t("J2", "eb_e2", 0, "n2_out", 0, "left")
    # Major westbound: through, plus a right turn into N2 that crosses eastbound traffic.
    t("J2", "wb_in", 0, "wb_e2", 0, "through")
    t("J2", "wb_in", 1, "wb_e2", 1, "through")
    t("J2", "wb_in", 1, "n2_out", 0, "right", yields=True)
    b.junction(
        "J2",
        "give_way",
        (J2_X - J2_HALF_X, J2_X + J2_HALF_X),
        (-major_half, J2_MINOR_Y),
        minor_approach_roads=("n2_in",),
    )


def _add_zones_and_labels(b: NetworkBuilder) -> None:
    b.zone("W", "eb_w4", "wb_w4")
    b.zone("E", "wb_in", "eb_out")
    b.zone("N1", "n1_in", "n1_out")
    b.zone("S1", "s1_in", "s1_out")
    b.zone("N2", "n2_in", "n2_out")
    b.annotate("J1 · signalised", 30, 30)
    b.annotate("J2 · give-way", J2_X + 20, 24)
    b.annotate(f"Flyover · deck +{DECK_Z:g} m", 120, 4.5, DECK_Z + 3)
    b.annotate("Diverge", -450, 20)
    b.annotate("Merge", 450, 16)
    b.annotate("Lane drop 3→2", X_DROP - 50, 16)
    b.annotate("4 lanes", X_WEST + 250, 20)
    b.annotate("3 lanes", 650, 16)
    b.annotate("2 lanes", 1000, 12)
    b.annotate("1 lane · 3.0 m", 220, 14)
    b.annotate("Minor road · 2.75 m", J2_X + 14, 200)
    b.annotate("Cross street · 3.25 m", 14, 250)


@lru_cache(maxsize=1)
def build_demo_network():
    """Build (once) and return the immutable demo network."""
    b = NetworkBuilder()
    add_corridor(b)
    _add_cross_streets(b)
    _add_j1_turns(b)
    _add_j2_turns(b)
    _add_zones_and_labels(b)
    meta = {
        "deck_z_m": DECK_Z,
        "deck_thickness_m": DECK_THICKNESS,
        "min_clearance_m": MIN_CLEARANCE,
        "median_half_m": MEDIAN_HALF,
    }
    return b.build(drive_side="left", meta=meta)
