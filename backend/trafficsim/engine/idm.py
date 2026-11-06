"""Vectorised IDM car-following, power/grade limit and the ballistic position update.

IDM (Treiber, Hennecke & Helbing 2000):
    a_IDM = a · [1 − (v/v0)^δ − (s*/s)²],   s* = s0 + max(0, v·T + v·Δv / (2·√(a·b)))
with δ = 4 written as x*x*x*x (no transcendental ufuncs in the hot path).

Power and grade (all classes; it is what makes trucks crawl up the ramp):
    a ≤ P/(m · max(v, V_TRACTION_MIN)) − g · (sinθ + c_r)

Ballistic update (Treiber & Kanagaraj 2015, "Comparing numerical integration schemes
for time-continuous car-following models"): v ≥ 0 by construction; a vehicle that would
reach v = 0 inside the step stops exactly at s + v²/(2|a|).
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.constants import DT, G
from trafficsim.engine.params.driving import ROLLING_RESISTANCE, V_TRACTION_MIN_MPS


def idm_accel(
    v: np.ndarray,
    v0: np.ndarray,
    T: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    s0: np.ndarray,
    gap: np.ndarray,
    dv: np.ndarray,
) -> np.ndarray:
    """IDM acceleration. ``gap`` = +inf means no leader; ``dv`` = v − v_leader."""
    x = v / v0
    free = 1.0 - x * x * x * x
    s_star = s0 + np.maximum(0.0, v * T + v * dv / (2.0 * np.sqrt(a * b)))
    has_leader = np.isfinite(gap)
    safe_gap = np.where(has_leader, gap, 1.0)
    if np.any(has_leader & (safe_gap <= 0.0)):
        raise FloatingPointError("non-positive gap passed to IDM (collision upstream)")
    ratio = s_star / safe_gap
    interaction = np.where(has_leader, ratio * ratio, 0.0)
    return a * (free - interaction)


def power_limited_accel(v: np.ndarray, p2m: np.ndarray, sin_theta: np.ndarray) -> np.ndarray:
    """Maximum tractive acceleration on the local grade [m/s²]."""
    return p2m / np.maximum(v, V_TRACTION_MIN_MPS) - G * (sin_theta + ROLLING_RESISTANCE)


def ballistic_update(
    s: np.ndarray, v: np.ndarray, acc: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    v_new = v + acc * DT
    stops = v_new < 0.0
    # For stopping vehicles acc < 0, so the stop distance v²/(2|acc|) is finite.
    acc_safe = np.where(stops, acc, -1.0)
    ds = np.where(stops, -(v * v) / (2.0 * acc_safe), v * DT + 0.5 * acc * DT * DT)
    return s + ds, np.where(stops, 0.0, v_new)
