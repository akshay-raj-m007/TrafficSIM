"""Lane changes: MOBIL (discretionary) with mandatory changes taking priority.

For a changer c, new follower n and old follower o (IDM accelerations, primes = after):
  safety     a'_n ≥ −b_safe  and  a'_c ≥ −b_safe,  both new gaps > 0
  incentive  a'_c − a_c + p·[(a'_n − a_n) + (a'_o − a_o)] > Δa_th ± keep-left bias
A vehicle whose lane does not lead onward on its route (diverge, turn lane, dropped
lane) makes a *mandatory* change toward the nearest good lane: no incentive test, and
b_safe rises toward B_SAFE_URGENT as the lane end approaches (gap acceptance). Mandatory
vehicles never change in the other direction; discretionary changes never enter a lane
that does not lead onward. Changes are applied in a deterministic order, and two changers
may not claim overlapping space in the same target lane in one step.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.engine.idm import idm_accel
from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.lc_neighbours import current_follower, target_neighbours
from trafficsim.engine.leaders import Occupancy
from trafficsim.engine.params.driving import (
    B_SAFE_URGENT_MPS2,
    D_URGENT_M,
    KEEP_LEFT_BIAS_MPS2,
    LC_COOLDOWN_S,
    LC_DECISION_INTERVAL_S,
    MOBIL_B_SAFE_MPS2,
    MOBIL_POLITENESS,
    MOBIL_THRESHOLD_MPS2,
)
from trafficsim.engine.routes import RouteTable, next_seg, refresh_lane_cache
from trafficsim.engine.transfer import LaneChangeEvent, TransferLog
from trafficsim.engine.vehicle import LEN, S0, A, B, T, VehicleState

DECISION_EVERY_STEPS = round(LC_DECISION_INTERVAL_S * STEPS_PER_SECOND)


def _idm(vs, lg, rows, segs, gap, v_lead):
    c = vs.cls[rows]
    v = vs.v[rows]
    return idm_accel(v, lg.v0_eff[segs, c], T[c], A[c], B[c], S0[c], gap, v - v_lead)


def _candidates(vs: VehicleState, lg: LaneGraph, tick: int):
    """Vectorised (rows, targets, mandatory, direction, urgency) of possible changes."""
    eligible = (~lg.is_conn[vs.seg]) & (vs.tail < 0) & (vs.lc_timer >= LC_COOLDOWN_S)
    # No lane changes within the comfortable stopping distance (+ s0) of a junction
    # stop line: the vehicle may already be committed there (solid lines before stop
    # lines). Uses each class's own b and s0; no new parameter.
    c = vs.cls
    to_line = lg.length[vs.seg] - vs.s
    eligible &= ~(lg.ends_at_junction[vs.seg] & (to_line < vs.v * vs.v / (2 * B[c]) + S0[c]))
    decides_now = (vs.vid + tick) % DECISION_EVERY_STEPS == 0
    eligible &= (vs.off != 0) | decides_now
    base = np.flatnonzero(eligible)
    off = vs.off[base].astype(np.int64)
    lane = lg.lane_index[vs.seg[base]].astype(np.int64)
    parts = []
    for d in (-1, 1):
        tg = lg.nbr[vs.seg[base], 0 if d < 0 else 1].astype(np.int64)
        good_t = (vs.goodbits[base] >> np.maximum(lane + d, 0)) & 1
        mand = (off != 0) & (np.sign(off) == d)
        disc = (off == 0) & (good_t == 1)
        keep = (tg >= 0) & (mand | disc)
        parts.append((base[keep], tg[keep], mand[keep], np.full(keep.sum(), d), off[keep]))
    rows, tgts, mand, dirs, offs = (np.concatenate(x) for x in zip(*parts, strict=True))
    per_lane = (lg.length[vs.seg[rows]] - vs.s[rows]) / np.maximum(np.abs(offs), 1)
    urg = np.clip(1.0 - per_lane / D_URGENT_M, 0.0, 1.0)
    return rows, tgts, mand, dirs, urg


def lane_changes(
    vs: VehicleState, lg: LaneGraph, rt: RouteTable, occ: Occupancy,
    gap: np.ndarray, v_lead: np.ndarray, tick: int, log: TransferLog, t_now: float,
) -> tuple[int, int]:  # fmt: skip
    """Apply this step's lane changes in place. Returns (changes, mandatory changes)."""
    rows, tgts, mand, dirs, urg = _candidates(vs, lg, tick)
    if rows.size == 0:
        return 0, 0
    nb = target_neighbours(vs, lg, rt, occ, rows, tgts)
    b_safe = np.where(mand, MOBIL_B_SAFE_MPS2 + (B_SAFE_URGENT_MPS2 - MOBIL_B_SAFE_MPS2) * urg,
                      MOBIL_B_SAFE_MPS2)  # fmt: skip
    ok = (nb.gap_lead > 0) & (nb.gap_fol > 0)
    a_c_new = np.full(rows.size, -np.inf)
    a_c_new[ok] = _idm(vs, lg, rows[ok], tgts[ok], nb.gap_lead[ok], nb.v_lead[ok])
    has_n = ok & (nb.fol_row >= 0)
    n = nb.fol_row[has_n]
    a_n_new = np.zeros(rows.size)
    a_n_old = np.zeros(rows.size)
    a_n_new[has_n] = _idm(vs, lg, n, vs.seg[n], nb.gap_fol[has_n], vs.v[rows[has_n]])
    a_n_old[has_n] = _idm(vs, lg, n, vs.seg[n], gap[n], v_lead[n])
    safe = ok & (a_c_new >= -b_safe) & (~has_n | (a_n_new >= -b_safe))

    a_c_old = _idm(vs, lg, rows, vs.seg[rows], gap[rows], v_lead[rows])
    o_row, o_gap = current_follower(vs, lg, occ, rows)
    has_o = o_row >= 0
    a_o_old = np.zeros(rows.size)
    a_o_new = np.zeros(rows.size)
    o = o_row[has_o]
    a_o_old[has_o] = _idm(vs, lg, o, vs.seg[o], o_gap[has_o], vs.v[rows[has_o]])
    merged_gap = o_gap[has_o] + LEN[vs.cls[rows[has_o]]] + gap[rows[has_o]]
    a_o_new[has_o] = _idm(vs, lg, o, vs.seg[o], merged_gap, v_lead[rows[has_o]])
    gain = a_c_new - a_c_old + MOBIL_POLITENESS * ((a_n_new - a_n_old) + (a_o_new - a_o_old))
    threshold = MOBIL_THRESHOLD_MPS2 + np.where(dirs < 0, -KEEP_LEFT_BIAS_MPS2, KEEP_LEFT_BIAS_MPS2)
    accept = safe & (mand | (gain > threshold))
    info = (nb.gap_lead, nb.gap_fol, np.where(has_n, a_n_new, 0.0), b_safe)
    return _apply(vs, lg, rt, rows, tgts, mand, gain, nb.s_t, accept, info, log, t_now)


def _pair_safe(vs, lg, tg: int, rear_row: int, gap: float, front_row: int, b_safe: float):
    """Would rear_row, following front_row at ``gap`` in lane tg, brake softer than b_safe?"""
    if gap <= 0.0:
        return False
    r = np.array([rear_row])
    a = _idm(vs, lg, r, np.array([tg]), np.array([gap]), vs.v[[front_row]])
    return bool(a[0] >= -b_safe)


def _apply(vs, lg, rt, rows, tgts, mand, gain, s_t, accept, info, log, t_now) -> tuple[int, int]:
    gap_lead, gap_lag, a_fol, b_safe = info
    idx = np.flatnonzero(accept)
    # Deterministic priority: mandatory first, then larger gain, then vehicle id.
    idx = idx[np.lexsort((vs.vid[rows[idx]], -gain[idx], ~mand[idx]))]
    moved: set[int] = set()
    claims: dict[int, list[tuple[int, float, float]]] = {}  # tg -> (row, front, rear)
    n_all = n_mand = 0
    for k in idx:
        i, tg = int(rows[k]), int(tgts[k])
        if i in moved:
            continue
        front, rear = float(s_t[k]), float(s_t[k] - LEN[vs.cls[i]])
        # Two changers entering the same lane in one step must also be safe w.r.t. each
        # other (same MOBIL criterion as against the vehicles already in the lane).
        clash = False
        for j, f_j, r_j in claims.get(tg, []):
            if front <= f_j:
                clash = not _pair_safe(vs, lg, tg, i, r_j - front, j, b_safe[k])
            else:
                clash = not _pair_safe(vs, lg, tg, j, rear - f_j, i, b_safe[k])
            if clash:
                break
        if clash:
            continue
        claims.setdefault(tg, []).append((i, front, rear))
        moved.add(i)
        log.lane_changes.append(
            LaneChangeEvent(
                t_now, int(vs.vid[i]), int(vs.seg[i]), tg, bool(mand[k]), float(gap_lead[k]),
                float(gap_lag[k]), float(a_fol[k]), float(b_safe[k]),
            )
        )  # fmt: skip
        vs.seg[i], vs.s[i], vs.lc_timer[i] = tg, s_t[k], 0.0
        vs.nxt[i] = next_seg(lg, rt, int(vs.route[i]), int(vs.rpos[i]), tg)
        refresh_lane_cache(vs, lg, rt, i)
        n_all += 1
        n_mand += int(mand[k])
    return n_all, n_mand
