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

# ------------------------------------------------------------ MOBIL --------------------
# Lane changing: MOBIL (Kesting, Treiber & Helbing 2007, Transp. Res. Rec. 1999:86-94).
# Politeness factor p [-]: weight of the gains/losses of affected followers.
MOBIL_POLITENESS: Final[float] = 0.2
# Changing threshold Δa_th [m/s²]: minimum net advantage for a discretionary change.
MOBIL_THRESHOLD_MPS2: Final[float] = 0.1
# Safe deceleration b_safe [m/s²]: the new follower may not be forced to brake harder.
MOBIL_B_SAFE_MPS2: Final[float] = 4.0
# Keep-left bias [m/s²] (left-hand traffic: keep to the kerb lane unless overtaking).
# Mirror of the "keep-right" asymmetry of Kesting et al. 2007 (typical 0.2-0.3 m/s² with a
# threshold of 0.1); it is added to the threshold for a change toward the median and
# subtracted for one toward the kerb. Two behaviours bound it, both measured on plain roads
# (README, "Lane utilisation", grid of 0.10-0.20):
#  * it must EXCEED the threshold: a car that has overtaken a truck and returns to the kerb
#    lane makes the truck behind it brake a little (politeness-weighted loss > 0), so with a
#    bias equal to the threshold (0.10) it never returns and hogs the median lane;
#  * it must stay SMALL: at 0.20 the median lane of a 4-lane road held 5 % of the vehicles at
#    1,200 veh/h (48/28/19/5 % kerb to median); at 0.125 it already drops to 14 %.
# 0.11 and 0.12 satisfy both (overtaker returns; every lane of 2-4 holds at least 17 %); 0.12
# is taken for the margin. A change toward the median then needs about 2.2 x the plain
# threshold of gain, one toward the kerb about a fifth of it.
KEEP_LEFT_BIAS_MPS2: Final[float] = 0.12
# Minimum time between two lane changes of one vehicle [s]; empirical lane-change
# durations are ~3–6 s (e.g. Toledo & Zohar 2007), we take the short end.
LC_COOLDOWN_S: Final[float] = 3.0

# Mandatory changes (wrong lane for the route: diverge, turn lane, lane drop / merge).
# Gap acceptance uses MOBIL's safety criterion only (no incentive test). As the end of
# the lane approaches, the acceptable follower deceleration rises linearly from
# MOBIL_B_SAFE_MPS2 (at D_URGENT_M or more per lane still to cross) to
# B_SAFE_URGENT_MPS2 (at the lane end) — drivers accept tighter gaps when they must.
# The urgent value stays well below the emergency-braking threshold above.
D_URGENT_M: Final[float] = 200.0
B_SAFE_URGENT_MPS2: Final[float] = 6.0
# Discretionary lane choice is reassessed once per this interval per vehicle (staggered
# by vehicle id so the work is spread over steps) [s]. Drivers do not re-decide every
# 0.1 s; ~1 s is the order of the perception–reaction time (e.g. Green 2000, "How long
# does it take to stop?", Transp. Human Factors 2:195-216). Mandatory changes (wrong
# lane for the route) are evaluated every step.
LC_DECISION_INTERVAL_S: Final[float] = 1.0
