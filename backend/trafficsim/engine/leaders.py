"""Leader search: for every vehicle, the gap to (and speed of) what it must follow.

Occupants of a segment are its vehicles plus *ghosts*: a vehicle that has just moved on
but whose rear still overlaps its previous segment appears there too (front position
beyond the segment end), so vehicles behind it on that segment — whatever path they
take — never ignore its tail. All occupants are sorted by (segment, s); a vehicle's
in-segment leader is the next occupant. Vehicles with no in-segment leader walk
downstream along their own path (Python loop over these front vehicles only) until a
vehicle, a blocked transition (stop line, wrong/dropped lane end) or LOOKAHEAD_M.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.params.driving import LOOKAHEAD_M
from trafficsim.engine.routes import NEXT_EXIT, NEXT_NONE, RouteTable, next_seg
from trafficsim.engine.vehicle import LEN, VehicleState

# gate(i, conn_seg) -> True if vehicle i may enter junction connector conn_seg now.
Gate = Callable[[int, int], bool]


@dataclass
class Occupancy:
    seg: np.ndarray  # occupant segment (sorted)
    s: np.ndarray  # occupant front position in that segment's coordinates
    length: np.ndarray
    v: np.ndarray
    first: dict[int, int]  # segment -> position (in sorted arrays) of its rearmost occupant
    pos_of: np.ndarray  # vehicle row -> its position in the sorted arrays


def build_occupancy(vs: VehicleState, lg: LaneGraph) -> Occupancy:
    n = vs.n
    lens = LEN[vs.cls]
    g = np.flatnonzero(vs.tail >= 0)
    seg = np.concatenate([vs.seg, vs.tail[g]])
    s = np.concatenate([vs.s, lg.length[vs.tail[g]] + vs.s[g]])
    order = np.lexsort((s, seg))
    seg_o = seg[order]
    starts = np.flatnonzero(np.r_[True, seg_o[1:] != seg_o[:-1]]) if seg_o.size else []
    pos_of = np.empty(n, dtype=np.int64)
    real = order < n
    pos_of[order[real]] = np.flatnonzero(real)
    return Occupancy(
        seg=seg_o,
        s=s[order],
        length=np.concatenate([lens, lens[g]])[order],
        v=np.concatenate([vs.v, vs.v[g]])[order],
        first={int(seg_o[p]): int(p) for p in starts},
        pos_of=pos_of,
    )


def find_leaders(
    vs: VehicleState, lg: LaneGraph, rt: RouteTable, occ: Occupancy, gate: Gate | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return (gap [m], leader speed [m/s]); gap = +inf when the road ahead is free."""
    n = vs.n
    gap = np.full(n, np.inf)
    v_lead = np.zeros(n)
    if n == 0:
        return gap, v_lead
    p = occ.pos_of
    has = (p + 1 < occ.seg.size) & (occ.seg[np.minimum(p + 1, occ.seg.size - 1)] == vs.seg)
    q = p[has] + 1
    gap[has] = occ.s[q] - occ.length[q] - vs.s[has]
    v_lead[has] = occ.v[q]
    for i in np.flatnonzero(~has):
        gap[i], v_lead[i] = _walk(int(i), vs, lg, rt, occ, gate)
    return gap, v_lead


def _walk(i, vs, lg, rt, occ, gate) -> tuple[float, float]:
    seg, nx, rpos, route = int(vs.seg[i]), int(vs.nxt[i]), int(vs.rpos[i]), int(vs.route[i])
    d = float(lg.length[seg] - vs.s[i])
    while d < LOOKAHEAD_M:
        if nx == NEXT_EXIT:
            return np.inf, 0.0
        if nx == NEXT_NONE:
            return d, 0.0  # lane ends with no way onward: stationary obstacle at the end
        if lg.is_conn[nx] and gate is not None and not gate(i, nx):
            return d, 0.0  # junction entry not permitted: stop at the line
        j = occ.first.get(nx)
        if j is not None:
            return d + float(occ.s[j] - occ.length[j]), float(occ.v[j])
        d += float(lg.length[nx])
        if not lg.is_conn[nx]:
            rpos += 1
        seg, nx = nx, next_seg(lg, rt, route, rpos, nx)
    return np.inf, 0.0
