"""Lane-change preparation ("synchronisation") for mandatory changers.

A vehicle that must change lanes also follows the target-lane vehicle whose front is
ahead of its own front: with IDM if it is already fully behind it, or by braking at its
comfortable deceleration b while they still overlap side by side. Preparation never
brakes harder than b. Only the vehicle that
is behind yields, so two vehicles that need to swap lanes cannot lock each other: the
rear one drops back, the front one changes, then the rear one changes. This is the
standard lane-change preparation idea (e.g. Hidas 2002, "Modelling lane changing and
merging in microscopic traffic simulation", Transp. Res. C 10:351-371), reduced to the
IDM framework; it introduces no new parameters (uses each class's own IDM b).
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.idm import idm_accel
from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.leaders import KEY_STRIDE, Occupancy
from trafficsim.engine.vehicle import S0, A, B, T, VehicleState


def mandatory_offsets(vs: VehicleState) -> np.ndarray:
    """Signed lanes to the nearest good lane per vehicle (0: fine or on a connector)."""
    return vs.off.astype(np.int64)


def sync_accel(
    vs: VehicleState, lg: LaneGraph, occ: Occupancy, offsets: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(rows, acceleration bound) for mandatory changers with a target-lane vehicle ahead."""
    rows = np.flatnonzero(offsets != 0)
    if rows.size == 0:
        return rows, np.zeros(0)
    side = (offsets[rows] > 0).astype(np.int64)
    tgt = lg.nbr[vs.seg[rows], side]
    has_t = tgt >= 0
    rows, tgt = rows[has_t], tgt[has_t]
    s_t = vs.s[rows] * lg.length[tgt] / lg.length[vs.seg[rows]]
    pos = np.searchsorted(occ.key, tgt * KEY_STRIDE + s_t, side="right")
    n_occ = occ.seg.size
    ahead = (pos < n_occ) & (occ.seg[np.minimum(pos, n_occ - 1)] == tgt)
    rows, s_t, j = rows[ahead], s_t[ahead], pos[ahead]
    if rows.size == 0:
        return rows, np.zeros(0)
    c = vs.cls[rows]
    v = vs.v[rows]
    gap = occ.s[j] - occ.length[j] - s_t
    behind = gap > 0.0
    acc = -B[c]  # still alongside: drop back at comfortable deceleration
    if np.any(behind):
        cb = c[behind]
        acc[behind] = idm_accel(
            v[behind], lg.v0_eff[vs.seg[rows[behind]], cb], T[cb], A[cb], B[cb], S0[cb],
            gap[behind], v[behind] - occ.v[j[behind]],
        )  # fmt: skip
    # Preparation is not collision avoidance (the other vehicle is in another lane):
    # it never demands more than the comfortable deceleration b, and a stopped vehicle
    # simply waits.
    acc = np.maximum(acc, -B[c])
    acc = np.where((v <= 0.0) & (acc < 0.0), 0.0, acc)
    return rows, acc
