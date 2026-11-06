"""Who would be ahead of / behind a vehicle if it moved into an adjacent lane.

Queries are vectorised with ``searchsorted`` on the occupancy's combined sort key; only
the misses (no occupant ahead/behind on the target segment itself) fall back to a
Python walk downstream (``leaders.walk_ahead``) or a look at the upstream segments.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.leaders import KEY_STRIDE, Occupancy, walk_ahead
from trafficsim.engine.routes import RouteTable, next_seg
from trafficsim.engine.vehicle import LEN, VehicleState


@dataclass
class Neighbours:
    s_t: np.ndarray  # changer's position on the target segment [m]
    gap_lead: np.ndarray  # changer → new leader [m] (+inf: free)
    v_lead: np.ndarray
    fol_row: np.ndarray  # new follower's vehicle row (-1: none within reach)
    gap_fol: np.ndarray  # new follower → changer [m]


def _last_real(occ: Occupancy, seg: int) -> int | None:
    j = occ.last.get(seg)
    while j is not None and j >= 0 and occ.seg[j] == seg and occ.ghost[j]:
        j -= 1
    if j is None or j < 0 or occ.seg[j] != seg:
        return None
    return j


def upstream_follower(lg: LaneGraph, occ: Occupancy, seg: int, s_rear: float):
    """Closest real vehicle on a predecessor of ``seg``; returns (row, gap) or (-1, inf)."""
    best = (-1, np.inf)
    for p in lg.pred[seg]:
        j = _last_real(occ, p)
        if j is not None:
            g = float(lg.length[p] - occ.s[j]) + s_rear
            if g < best[1]:
                best = (int(occ.row[j]), g)
    return best


def target_neighbours(
    vs: VehicleState, lg: LaneGraph, rt: RouteTable, occ: Occupancy, rows: np.ndarray,
    targets: np.ndarray,
) -> Neighbours:  # fmt: skip
    m = rows.size
    s_t = vs.s[rows] * lg.length[targets] / lg.length[vs.seg[rows]]
    own_len = LEN[vs.cls[rows]]
    pos = np.searchsorted(occ.key, targets * KEY_STRIDE + s_t, side="left")
    n_occ = occ.seg.size
    lead_ok = (pos < n_occ) & (occ.seg[np.minimum(pos, n_occ - 1)] == targets)
    prev = np.maximum(pos - 1, 0)
    fol_ok = (pos >= 1) & (occ.seg[prev] == targets) & ~occ.ghost[prev]

    gap_lead = np.full(m, np.inf)
    v_lead = np.zeros(m)
    q = pos[lead_ok]
    gap_lead[lead_ok] = occ.s[q] - occ.length[q] - s_t[lead_ok]
    v_lead[lead_ok] = occ.v[q]
    for k in np.flatnonzero(~lead_ok):
        i, tg = int(rows[k]), int(targets[k])
        nx = next_seg(lg, rt, int(vs.route[i]), int(vs.rpos[i]), tg)
        gap_lead[k], v_lead[k] = walk_ahead(
            lg, rt, occ, tg, float(s_t[k]), nx, int(vs.rpos[i]), int(vs.route[i])
        )

    fol_row = np.full(m, -1, dtype=np.int64)
    gap_fol = np.full(m, np.inf)
    fol_row[fol_ok] = occ.row[prev[fol_ok]]
    gap_fol[fol_ok] = s_t[fol_ok] - own_len[fol_ok] - occ.s[prev[fol_ok]]
    for k in np.flatnonzero(~fol_ok):
        fol_row[k], gap_fol[k] = upstream_follower(
            lg, occ, int(targets[k]), float(s_t[k] - own_len[k])
        )
    return Neighbours(s_t, gap_lead, v_lead, fol_row, gap_fol)


def current_follower(vs: VehicleState, lg: LaneGraph, occ: Occupancy, rows: np.ndarray):
    """Vehicle directly behind each changer in its current lane: (rows, gaps)."""
    p = occ.pos_of[rows] - 1
    pc = np.maximum(p, 0)
    ok = (p >= 0) & (occ.seg[pc] == vs.seg[rows]) & ~occ.ghost[pc]
    own_rear = vs.s[rows] - LEN[vs.cls[rows]]
    out_row = np.full(rows.size, -1, dtype=np.int64)
    out_gap = np.full(rows.size, np.inf)
    out_row[ok] = occ.row[pc[ok]]
    out_gap[ok] = own_rear[ok] - occ.s[pc[ok]]
    for k in np.flatnonzero(~ok):
        out_row[k], out_gap[k] = upstream_follower(
            lg, occ, int(vs.seg[rows[k]]), float(own_rear[k])
        )
    return out_row, out_gap
