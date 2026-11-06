"""Driving-behaviour parameters (car-following, physics, insertion, lane width).

Every value carries its unit in the name or comment and a source/rationale.
"""

from typing import Final

# ---------------------------------------------------------------- IDM ------------------
# Acceleration exponent δ of the Intelligent Driver Model [-]
# (Treiber, Hennecke & Helbing 2000, Phys. Rev. E 62:1805). Implemented as x*x*x*x.
IDM_DELTA: Final[int] = 4

# Deceleration above which a step is counted as "emergency braking" [m/s²]. Diagnostic
# only — braking is never capped (a cap is what lets collisions happen). ~0.9 g, the
# order of the maximum tyre–road deceleration on dry asphalt.
B_EMERGENCY_MPS2: Final[float] = 9.0

# How far ahead a driver scans for leaders / stop lines / lane ends [m]. Must exceed the
# comfortable stopping distance v²/(2b) at the highest desired speed: (16.7 m/s)² /
# (2 · 1.5 m/s²) ≈ 93 m, and the IDM interaction range s0 + vT + v·Δv/(2√(ab)).
LOOKAHEAD_M: Final[float] = 250.0

# ---------------------------------------------------------- physics --------------------
# Below this speed the power limit P/(m·v) is not applied (traction-limited regime; the
# class's IDM `a` governs instead) [m/s]. Avoids the P/(m·v) → ∞ singularity at v = 0.
V_TRACTION_MIN_MPS: Final[float] = 1.0

# Rolling-resistance coefficient, tyre on asphalt [-]. Typical range 0.008–0.015
# (e.g. Wong, "Theory of Ground Vehicles", 4th ed.).
ROLLING_RESISTANCE: Final[float] = 0.010

# Comfortable lateral acceleration in junction turns [m/s²]; sets the turn-speed limit
# v = sqrt(a_lat · R) from each turn path's minimum radius. Observed urban turning
# manoeuvres lie roughly in 2–4 m/s²; we take the middle.
A_LAT_COMFORT_MPS2: Final[float] = 3.0

# -------------------------------------------------------- lane width -------------------
# HCM-inspired lane-width speed model (NOT the HCM procedure), proportional form:
#   v0_eff = min(v0_class, speed limit) · (1 − K_W · max(0, W_REF − w))
# W_REF is the HCM base lane width (12 ft). K_W is the HCM 6th ed. basic-freeway
# lane-width adjustment (Exhibit 12-20: −6.0 mi/h for 10 ft vs 12 ft lanes) expressed as
# a FRACTION of the HCM base free-flow speed (75.4 mi/h, Eq. 12-2): (6.0/75.4) per 2 ft
# = 0.1305 per metre. Proportional rather than absolute because subtracting a freeway
# km/h figure from a 30 km/h urban road would cut its speed by ~half. HCM tabulates
# only down to 10 ft (3.05 m); our 3.0 m and 2.75 m lanes are a linear extrapolation.
LANE_WIDTH_REF_M: Final[float] = 3.65
HCM_BASE_FFS_MPH: Final[float] = 75.4
HCM_LANE_WIDTH_ADJ_MPH: Final[float] = 6.0  # for 10 ft vs 12 ft lanes
LANE_WIDTH_SPEED_FRACTION_PER_M: Final[float] = (
    HCM_LANE_WIDTH_ADJ_MPH / HCM_BASE_FFS_MPH / (2 * 0.3048)
)

# --------------------------------------------------------- insertion -------------------
# A queued vehicle is inserted at the start of its entry lane only if the gap to the
# vehicle ahead is at least s0 + v_ins·T (the IDM desired gap with zero approach rate),
# with v_ins = min(v0_eff, v_leader, (gap − s0)/T). If even v_ins = 0 does not fit
# (gap < s0) the vehicle stays in the entry queue as unserved demand.
# (No extra constant needed: the rule uses each class's own s0 and T.)
