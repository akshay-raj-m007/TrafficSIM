"""East-west corridor of the demo network: arterial, flyover + ramps, lane drop.

Layout (x east, y north, metres; left-hand traffic, so eastbound runs on the north
side of the median). Eastbound:

  x=-1000 ──4 lanes── -450 ┬─ 2 surface lanes ──▶ J1 (x=0) ──1 lane──┐ +450 ──3 lanes── +900
                           └─ ramp ↑ ── flyover deck z=6.5 m ── ramp ↓ ┘     (kerb lane ends:
                                                                             lane drop 3→2)
Westbound mirrors it: 2 lanes from J2, widening 2→3 at +900, diverge at +450 (1 surface
lane to J1, 2 to the flyover), merge at -450 into 4 lanes.

The diverge and merge are lane-level: median-side lanes continue onto the ramps, kerb
lanes onto the surface road, at exactly matching lateral positions.
"""

from __future__ import annotations

from trafficsim.network import geometry as geo
from trafficsim.network.builder import NetworkBuilder

# Lateral layout [m]
MEDIAN_HALF = 1.0  # half-width of the central median
W_ART = 3.5  # arterial / flyover lane width
W_SURF1 = 3.0  # narrow single-lane surface links next to J1
SURF2_INNER = MEDIAN_HALF + 2 * W_ART  # 2-lane surface roads sit outside the flyover
# single narrow lane centred on the 2-lane road's median-side lane (y = ±9.75)
SURF1_INNER = SURF2_INNER + W_ART / 2 - W_SURF1 / 2

# Longitudinal layout [m]
X_WEST, X_EAST = -1000.0, 1500.0
X_DIVERGE, X_MERGE = -450.0, 450.0
X_DECK_START, X_DECK_END = -270.0, 270.0
X_DROP = 900.0  # end of the 3-lane section (lane-drop taper drawn over the last 100 m)
J1_HALF_X, J1_HALF_Y = 15.0, 20.0
J2_X, J2_HALF_X, J2_MINOR_Y = 1100.0, 12.0, 12.0

# Vertical layout [m]
DECK_Z = 6.5  # running surface of the flyover deck
DECK_THICKNESS = 1.0
MIN_CLEARANCE = 5.5  # soffit to road surface below


def _corr(b: NetworkBuilder, rid, kind, x0, x1, widths, inner, kmh, z0=0.0, z1=None):
    ref = geo.straight(x0, 0.0, x1, 0.0, z0) if z1 is None else geo.graded(x0, 0, x1, 0, z0, z1)
    return b.road(rid, kind, ref, widths, inner, kmh)


def add_corridor(b: NetworkBuilder) -> None:
    a2, a3, a4 = [W_ART] * 2, [W_ART] * 3, [W_ART] * 4
    j2w, j2e = J2_X - J2_HALF_X, J2_X + J2_HALF_X

    # ---- eastbound
    _corr(b, "eb_w4", "surface", X_WEST, X_DIVERGE, a4, MEDIAN_HALF, 50)
    _corr(b, "eb_surf_w", "surface", X_DIVERGE, -J1_HALF_X, a2, SURF2_INNER, 40)
    _corr(b, "eb_ramp_up", "ramp", X_DIVERGE, X_DECK_START, a2, MEDIAN_HALF, 50, 0.0, DECK_Z)
    _corr(b, "eb_flyover", "flyover", X_DECK_START, X_DECK_END, a2, MEDIAN_HALF, 60, DECK_Z)
    _corr(b, "eb_ramp_dn", "ramp", X_DECK_END, X_MERGE, a2, MEDIAN_HALF, 50, DECK_Z, 0.0)
    _corr(b, "eb_surf_e", "surface", J1_HALF_X, X_MERGE, [W_SURF1], SURF1_INNER, 40)
    _corr(b, "eb_e3", "surface", X_MERGE, X_DROP, a3, MEDIAN_HALF, 50)
    _corr(b, "eb_e2", "surface", X_DROP, j2w, a2, MEDIAN_HALF, 50)
    _corr(b, "eb_out", "surface", j2e, X_EAST, a2, MEDIAN_HALF, 50)

    # ---- westbound
    _corr(b, "wb_in", "surface", X_EAST, j2e, a2, MEDIAN_HALF, 50)
    _corr(b, "wb_e2", "surface", j2w, X_DROP, a2, MEDIAN_HALF, 50)
    _corr(b, "wb_e3", "surface", X_DROP, X_MERGE, a3, MEDIAN_HALF, 50)
    _corr(b, "wb_surf_e", "surface", X_MERGE, J1_HALF_X, [W_SURF1], SURF1_INNER, 40)
    _corr(b, "wb_ramp_up", "ramp", X_MERGE, X_DECK_END, a2, MEDIAN_HALF, 50, 0.0, DECK_Z)
    _corr(b, "wb_flyover", "flyover", X_DECK_END, X_DECK_START, a2, MEDIAN_HALF, 60, DECK_Z)
    _corr(b, "wb_ramp_dn", "ramp", X_DECK_START, X_DIVERGE, a2, MEDIAN_HALF, 50, DECK_Z, 0.0)
    _corr(b, "wb_surf_w", "surface", -J1_HALF_X, X_DIVERGE, a2, SURF2_INNER, 40)
    _corr(b, "wb_w4", "surface", X_DIVERGE, X_WEST, a4, MEDIAN_HALF, 50)

    # ---- eastbound lane-level links
    b.link("eb_w4", 0, "eb_surf_w", 0)  # diverge: kerb lanes stay on the surface
    b.link("eb_w4", 1, "eb_surf_w", 1)
    b.link("eb_w4", 2, "eb_ramp_up", 0)  # median lanes climb onto the flyover
    b.link("eb_w4", 3, "eb_ramp_up", 1)
    b.link("eb_ramp_up", 0, "eb_flyover", 0)
    b.link("eb_ramp_up", 1, "eb_flyover", 1)
    b.link("eb_flyover", 0, "eb_ramp_dn", 0)
    b.link("eb_flyover", 1, "eb_ramp_dn", 1)
    b.link("eb_surf_e", 0, "eb_e3", 0)  # merge: 1 surface + 2 ramp lanes = 3 lanes
    b.link("eb_ramp_dn", 0, "eb_e3", 1)
    b.link("eb_ramp_dn", 1, "eb_e3", 2)
    b.link("eb_e3", 1, "eb_e2", 0)  # lane drop: eb_e3 lane 0 has no successor
    b.link("eb_e3", 2, "eb_e2", 1)

    # ---- westbound lane-level links
    b.link("wb_e2", 0, "wb_e3", 1)  # widening 2→3: wb_e3 lane 0 is entered by lane change
    b.link("wb_e2", 1, "wb_e3", 2)
    b.link("wb_e3", 0, "wb_surf_e", 0)  # diverge
    b.link("wb_e3", 1, "wb_ramp_up", 0)
    b.link("wb_e3", 2, "wb_ramp_up", 1)
    b.link("wb_ramp_up", 0, "wb_flyover", 0)
    b.link("wb_ramp_up", 1, "wb_flyover", 1)
    b.link("wb_flyover", 0, "wb_ramp_dn", 0)
    b.link("wb_flyover", 1, "wb_ramp_dn", 1)
    b.link("wb_surf_w", 0, "wb_w4", 0)  # merge: 2 surface + 2 ramp lanes = 4 lanes
    b.link("wb_surf_w", 1, "wb_w4", 1)
    b.link("wb_ramp_dn", 0, "wb_w4", 2)
    b.link("wb_ramp_dn", 1, "wb_w4", 3)
