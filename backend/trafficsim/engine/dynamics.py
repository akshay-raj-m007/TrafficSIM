"""Longitudinal dynamics for one step: IDM, power/grade limit, speed-limit anticipation.

acc = min(a_IDM, a_power, a_anticipation) where
  * a_IDM uses the vehicle's desired speed on its current segment (lane-width model and
    turn-curvature limit already folded into ``LaneGraph.v0_eff``);
  * a_power is the tractive limit on the local grade (idm.power_limited_accel);
  * a_anticipation is the constant deceleration that brings the vehicle down to the
    desired speed of its next segment exactly at the segment boundary,
    (v_next² − v²) / (2·d), applied only when v exceeds that next desired speed.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.idm import idm_accel, power_limited_accel
from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.params.driving import LOOKAHEAD_M
from trafficsim.engine.vehicle import P2M, S0, A, B, T, VehicleState


def sin_theta(vs: VehicleState, lg: LaneGraph) -> np.ndarray:
    out = np.zeros(vs.n)
    for seg, (s_mid, sin_t) in lg.profiles.items():
        on = vs.seg == seg
        if np.any(on):
            out[on] = np.interp(vs.s[on], s_mid, sin_t)
    return out


def accelerations(
    vs: VehicleState, lg: LaneGraph, gap: np.ndarray, v_lead: np.ndarray, stop_gap: np.ndarray
) -> np.ndarray:
    c = vs.cls
    v = vs.v
    v0 = lg.v0_eff[vs.seg, c]
    acc = idm_accel(v, v0, T[c], A[c], B[c], S0[c], gap, v - v_lead)
    # Own stopping point (lane end / closed junction entry): IDM against a standing
    # obstacle there, combined with the leader constraint by taking the minimum.
    stops = np.isfinite(stop_gap)
    if np.any(stops):
        cs = c[stops]
        a_stop = idm_accel(
            v[stops], v0[stops], T[cs], A[cs], B[cs], S0[cs], stop_gap[stops], v[stops]
        )
        acc[stops] = np.minimum(acc[stops], a_stop)
    acc = np.minimum(acc, power_limited_accel(v, P2M[c], sin_theta(vs, lg)))

    has_next = vs.nxt >= 0
    d = lg.length[vs.seg] - vs.s
    v_next = np.where(has_next, lg.v0_eff[np.maximum(vs.nxt, 0), c], np.inf)
    anticipate = has_next & (v > v_next) & (d > 0.0) & (d < LOOKAHEAD_M)
    if np.any(anticipate):
        d_a = d[anticipate]
        a_ant = (v_next[anticipate] ** 2 - v[anticipate] ** 2) / (2.0 * d_a)
        acc[anticipate] = np.minimum(acc[anticipate], a_ant)
    return acc
