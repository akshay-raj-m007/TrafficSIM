"""East-west corridor of the demo network: arterial, flyover + ramps, lane drop.

Layout (x east, y north, metres; left-hand traffic, so eastbound runs on the north
side of the median). Eastbound, for the default structure (2 surface + 2 flyover lanes):

  x=-1000 ──4 lanes── -450 ┬─ 2 surface lanes ──▶ J1 (x=0) ──2 lanes──┐ +450 ──4 lanes── +900
                           └─ ramp ↑ ── flyover deck z=6.5 m ── ramp ↓ ─┘     (kerb lanes end:
                                                                              lane drop 4→2)
Westbound mirrors it: F lanes from J2, widening F→S+F at +900, diverge at +450 (S surface
lanes to J1, F to the flyover), merge at -450 into S+F lanes.

With S surface lanes (width Ws) and F flyover lanes (width Wf) (network/structure.py) the west
arterial has S+F lanes: kerb-side S go to the surface road, the median-side F to the ramps; the
east section has the F flyover lanes plus S link lanes, which continue the surface lanes east of
J1 (same count, width and position) and end at the lane drop, so the surface setting means what it
says downstream too.

The diverge and merge are lane-level: median-side lanes continue onto the ramps, kerb
lanes onto the surface road, at exactly matching lateral positions.
"""

from __future__ import annotations

from trafficsim.network import geometry as geo
from trafficsim.network.builder import NetworkBuilder
from trafficsim.network.demo_geometry import MEDIAN_HALF, Derived
from trafficsim.network.structure import Structure

# Longitudinal layout [m]
X_WEST, X_EAST = -1000.0, 1500.0
X_DIVERGE, X_MERGE = -450.0, 450.0
X_DECK_START, X_DECK_END = -270.0, 270.0
X_DROP = 900.0  # end of the S+F-lane section (lane-drop taper drawn over the last 100 m)
J1_HALF_X = 15.0
J2_X, J2_HALF_X = 1100.0, 12.0

# Vertical layout [m]
DECK_Z = 6.5  # running surface of the flyover deck
DECK_THICKNESS = 1.0
MIN_CLEARANCE = 5.5  # soffit to road surface below


def _corr(b: NetworkBuilder, rid, kind, x0, x1, widths, inner, kmh, z0=0.0, z1=None):
    ref = geo.straight(x0, 0.0, x1, 0.0, z0) if z1 is None else geo.graded(x0, 0, x1, 0, z0, z1)
    return b.road(rid, kind, ref, widths, inner, kmh)


def add_corridor(b: NetworkBuilder, st: Structure, d: Derived) -> None:
    s, f = st.surface_lanes, st.flyover_lanes
    surf, fly = [st.surface_width_m] * s, [st.flyover_width_m] * f
    west = surf + fly  # kerb lane first: the surface lanes, then the flyover lanes
    sect3 = surf + fly  # east section: the S link lanes (kerb side) + the flyover lanes
    j2w, j2e = J2_X - J2_HALF_X, J2_X + J2_HALF_X

    # ---- eastbound
    _corr(b, "eb_w4", "surface", X_WEST, X_DIVERGE, west, MEDIAN_HALF, 50)
    _corr(b, "eb_surf_w", "surface", X_DIVERGE, -J1_HALF_X, surf, d.surf_inner, 40)
    _corr(b, "eb_ramp_up", "ramp", X_DIVERGE, X_DECK_START, fly, MEDIAN_HALF, 50, 0.0, DECK_Z)
    _corr(b, "eb_flyover", "flyover", X_DECK_START, X_DECK_END, fly, MEDIAN_HALF, 60, DECK_Z)
    _corr(b, "eb_ramp_dn", "ramp", X_DECK_END, X_MERGE, fly, MEDIAN_HALF, 50, DECK_Z, 0.0)
    _corr(b, "eb_surf_e", "surface", J1_HALF_X, X_MERGE, surf, d.surf_inner, 40)
    _corr(b, "eb_e3", "surface", X_MERGE, X_DROP, sect3, MEDIAN_HALF, 50)
    _corr(b, "eb_e2", "surface", X_DROP, j2w, fly, MEDIAN_HALF, 50)
    _corr(b, "eb_out", "surface", j2e, X_EAST, fly, MEDIAN_HALF, 50)

    # ---- westbound
    _corr(b, "wb_in", "surface", X_EAST, j2e, fly, MEDIAN_HALF, 50)
    _corr(b, "wb_e2", "surface", j2w, X_DROP, fly, MEDIAN_HALF, 50)
    _corr(b, "wb_e3", "surface", X_DROP, X_MERGE, sect3, MEDIAN_HALF, 50)
    _corr(b, "wb_surf_e", "surface", X_MERGE, J1_HALF_X, surf, d.surf_inner, 40)
    _corr(b, "wb_ramp_up", "ramp", X_MERGE, X_DECK_END, fly, MEDIAN_HALF, 50, 0.0, DECK_Z)
    _corr(b, "wb_flyover", "flyover", X_DECK_END, X_DECK_START, fly, MEDIAN_HALF, 60, DECK_Z)
    _corr(b, "wb_ramp_dn", "ramp", X_DECK_START, X_DIVERGE, fly, MEDIAN_HALF, 50, DECK_Z, 0.0)
    _corr(b, "wb_surf_w", "surface", -J1_HALF_X, X_DIVERGE, surf, d.surf_inner, 40)
    _corr(b, "wb_w4", "surface", X_DIVERGE, X_WEST, west, MEDIAN_HALF, 50)

    # ---- eastbound lane-level links (stage by stage, in the original order)
    for k in range(s):  # diverge: kerb lanes stay on the surface
        b.link("eb_w4", k, "eb_surf_w", k)
    for i in range(f):  # median lanes climb onto the flyover
        b.link("eb_w4", s + i, "eb_ramp_up", i)
    for road_a, road_b in (("eb_ramp_up", "eb_flyover"), ("eb_flyover", "eb_ramp_dn")):
        for i in range(f):
            b.link(road_a, i, road_b, i)
    for k in range(s):  # the link lanes continue the surface lanes
        b.link("eb_surf_e", k, "eb_e3", k)
    for i in range(f):  # merge: the S link lanes + F ramp lanes
        b.link("eb_ramp_dn", i, "eb_e3", s + i)
    for i in range(f):
        b.link("eb_e3", s + i, "eb_e2", i)  # lane drop: the S link lanes have no successor

    # ---- westbound lane-level links
    for i in range(f):
        b.link("wb_e2", i, "wb_e3", s + i)  # widening: the S link lanes are entered by lane change
    for k in range(s):  # diverge: the S kerb-side lanes go to J1
        b.link("wb_e3", k, "wb_surf_e", k)
    for i in range(f):
        b.link("wb_e3", s + i, "wb_ramp_up", i)
    for road_a, road_b in (("wb_ramp_up", "wb_flyover"), ("wb_flyover", "wb_ramp_dn")):
        for i in range(f):
            b.link(road_a, i, road_b, i)
    for k in range(s):  # merge: S surface lanes + F ramp lanes
        b.link("wb_surf_w", k, "wb_w4", k)
    for i in range(f):
        b.link("wb_ramp_dn", i, "wb_w4", s + i)
