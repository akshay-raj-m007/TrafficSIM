"""The hand-built demo network (not from OpenStreetMap).

Contains every element the brief requires:
  * J1 — 4-arm signalised junction at x=0 (cross street N1/S1, 2+2 lanes, 3.25 m);
    the flyover deck passes over it.
  * J2 — give-way T-junction at x=1100; minor road N2 yields. Its approach has a left-turn
    lane and a right-turn lane (a flared approach, so a waiting right-turner, which must
    cross the whole major road, does not block left-turners); the exit lane is single.
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
    J2_HALF_X,
    J2_X,
    MIN_CLEARANCE,
    X_DROP,
    X_MERGE,
    X_WEST,
    add_corridor,
)
from trafficsim.network.demo_geometry import MEDIAN_HALF, Derived
from trafficsim.network.structure import Structure

W_CROSS = 3.25  # J1 cross-street lanes
W_MINOR = 2.75  # narrow minor road at J2
ARM_LEN = 400.0  # length of the cross-street arms from the corridor centreline


def _add_cross_streets(b: NetworkBuilder, st: Structure, d: Derived) -> None:
    c2 = [W_CROSS, W_CROSS]
    h = d.j1_half_y
    # J1 cross street (x = 0). Southbound lanes sit east of the centreline (LHT).
    b.road("n1_in", "surface", geo.straight(0, ARM_LEN, 0, h), c2, 0.5, 40)
    b.road("n1_out", "surface", geo.straight(0, h, 0, ARM_LEN), c2, 0.5, 40)
    b.road("s1_in", "surface", geo.straight(0, -ARM_LEN, 0, -h), c2, 0.5, 40)
    b.road("s1_out", "surface", geo.straight(0, -h, 0, -ARM_LEN), c2, 0.5, 40)
    # J2 minor road (x = 1100), no median: `j2_minor_lanes` approach lanes (southbound lanes
    # lie east of the centreline: lane 0 = kerb/left side, last lane = median side), one exit lane.
    lanes = st.j2_minor_lanes
    b.road("n2_in", "surface", geo.straight(J2_X, ARM_LEN, J2_X, d.j2_stop_y),
           [W_MINOR] * lanes, 0.0, 30)  # fmt: skip
    b.road("n2_out", "surface", geo.straight(J2_X, d.j2_exit_y, J2_X, ARM_LEN), [W_MINOR], 0.0, 30)


def _add_j1_turns(b: NetworkBuilder, st: Structure, d: Derived) -> None:
    t, s = b.turn, st.surface_lanes
    far = s - 1  # the median-side surface lane
    # West arm (eastbound approach, S lanes): kerb lane turns left, the middle lanes go
    # straight, the last lane goes straight and turns right. One lane does everything.
    for k in range(s):
        if k == 0:
            t("J1", "eb_surf_w", 0, "n1_out", 0, "left")
        if k > 0 or s == 1:
            t("J1", "eb_surf_w", k, "eb_surf_e", 0, "through")
        if k == far:
            t("J1", "eb_surf_w", k, "s1_out", 1, "right")
    # East arm (westbound approach, single narrow lane).
    t("J1", "wb_surf_e", 0, "s1_out", 0, "left")
    t("J1", "wb_surf_e", 0, "wb_surf_w", far, "through")
    t("J1", "wb_surf_e", 0, "n1_out", 1, "right")
    # North arm (southbound approach).
    t("J1", "n1_in", 0, "eb_surf_e", 0, "left")
    t("J1", "n1_in", 0, "s1_out", 0, "through")
    t("J1", "n1_in", 1, "s1_out", 1, "through")
    t("J1", "n1_in", 1, "wb_surf_w", far, "right")
    # South arm (northbound approach).
    t("J1", "s1_in", 0, "wb_surf_w", 0, "left")
    t("J1", "s1_in", 0, "n1_out", 0, "through")
    t("J1", "s1_in", 1, "n1_out", 1, "through")
    t("J1", "s1_in", 1, "eb_surf_e", 0, "right")
    h = d.j1_half_y
    b.junction("J1", "signalised", (-J1_HALF_X, J1_HALF_X), (-h, h))


def _add_j2_turns(b: NetworkBuilder, st: Structure, d: Derived) -> None:
    t, f = b.turn, st.flyover_lanes
    # Minor approach (southbound from N2) gives way to all major-road traffic. Left turns
    # leave from the kerb lane; right turns (which cross the whole major road) from the
    # last lane. With a single approach lane (j2_minor_lanes = 1) both share lane 0.
    t("J2", "n2_in", 0, "eb_out", 0, "left", yields=True)
    t("J2", "n2_in", st.j2_minor_lanes - 1, "wb_e2", f - 1, "right", yields=True)
    # Major eastbound: through, plus a left turn into N2 (no opposing stream in LHT).
    for k in range(f):
        t("J2", "eb_e2", k, "eb_out", k, "through")
    t("J2", "eb_e2", 0, "n2_out", 0, "left")
    # Major westbound: through, plus a right turn into N2 that crosses eastbound traffic.
    for k in range(f):
        t("J2", "wb_in", k, "wb_e2", k, "through")
    t("J2", "wb_in", f - 1, "n2_out", 0, "right", yields=True)
    b.junction(
        "J2",
        "give_way",
        (J2_X - J2_HALF_X, J2_X + J2_HALF_X),
        (-d.major_half, d.j2_stop_y),
        minor_approach_roads=("n2_in",),
    )


def _lanes(n: int) -> str:
    return f"{n} lane" if n == 1 else f"{n} lanes"


def _add_zones_and_labels(b: NetworkBuilder, st: Structure, d: Derived) -> None:
    s, f, wf = st.surface_lanes, st.flyover_lanes, st.flyover_width_m
    y3 = MEDIAN_HALF + (f + 1) * wf + 4.5  # label height above the (F+1)-lane section
    b.zone("W", "eb_w4", "wb_w4")
    b.zone("E", "wb_in", "eb_out")
    b.zone("N1", "n1_in", "n1_out")
    b.zone("S1", "s1_in", "s1_out")
    b.zone("N2", "n2_in", "n2_out")
    b.annotate("J1 · signalised", 30, 30)
    b.annotate("J2 · give-way", J2_X + 20, 24)
    b.annotate(f"Flyover · deck +{DECK_Z:g} m", 120, MEDIAN_HALF + f * wf / 2, DECK_Z + 3)
    b.annotate("Diverge", -450, d.j1_half_y)
    b.annotate("Merge", X_MERGE, y3)
    b.annotate(f"Lane drop {f + 1}→{f}", X_DROP - 50, y3)
    b.annotate(_lanes(s + f), X_WEST + 250, d.j1_half_y)
    b.annotate(_lanes(f + 1), 650, y3)
    b.annotate(_lanes(f), 1000, d.major_half + 4.0)
    b.annotate(f"1 lane · {d.link_width:.1f} m", 220, d.link_y + 4.25)
    b.annotate("Minor road · 2.75 m", J2_X + 14, 200)
    b.annotate("Cross street · 3.25 m", 14, 250)


@lru_cache(maxsize=64)
def _build(st: Structure):
    d = Derived.of(st)
    b = NetworkBuilder()
    add_corridor(b, st, d)
    _add_cross_streets(b, st, d)
    _add_j1_turns(b, st, d)
    _add_j2_turns(b, st, d)
    _add_zones_and_labels(b, st, d)
    meta = {
        "deck_z_m": DECK_Z,
        "deck_thickness_m": DECK_THICKNESS,
        "min_clearance_m": MIN_CLEARANCE,
        "median_half_m": MEDIAN_HALF,
    }
    return b.build(drive_side="left", meta=meta)


def build_demo_network(structure: Structure | int = 2):
    """Build (once per structure) and return the immutable demo network.

    An int is the J2 minor-approach lane count (1 = the original single shared lane, 2 = the
    flared approach) with the default arterial; a ``Structure`` sets the lane groups too.
    """
    if isinstance(structure, int) and not isinstance(structure, bool):
        if structure not in (1, 2):
            raise ValueError("minor_approach_lanes must be 1 or 2")
        structure = Structure(j2_minor_lanes=structure)
    return _build(structure)
