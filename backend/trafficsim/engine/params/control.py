"""Junction-control parameters (give-way, incidents; signals are added in part 4).

Every value carries its unit and source.
"""

from typing import Final

# ------------------------------------------------------------- give-way ----------------
# Base critical headways at a two-way stop/yield-controlled junction, HCM 6th ed.
# Exhibit 20-11, mirrored for left-hand traffic, indexed by the number of lanes per
# direction on the major road (1 = "two-lane major", 2 = "four-lane major"):
#   HCM minor-road RIGHT turn (no crossing; ours: minor LEFT)        6.2 s / 6.9 s
#   HCM minor-road LEFT turn (crosses the major road; ours: RIGHT)   7.1 s / 7.5 s
#   HCM major-road LEFT turn (crosses opposing; ours: major RIGHT)   4.1 s / 4.1 s
# A major road with more than 2 lanes per direction (a structural setting) is not tabulated by
# HCM: it uses the 2-lanes values, the largest tabulated.
# A yielding vehicle enters only if every approaching vehicle on a conflicting priority
# movement is at least this many seconds (at its current speed) from its stop line.
CRITICAL_GAP_MINOR_LEFT_S: Final[dict[int, float]] = {1: 6.2, 2: 6.9}
CRITICAL_GAP_MINOR_RIGHT_S: Final[dict[int, float]] = {1: 7.1, 2: 7.5}
CRITICAL_GAP_MAJOR_RIGHT_S: Final[dict[int, float]] = {1: 4.1, 2: 4.1}
# HCM follow-up headways (Exhibit 20-11) — NOT used by the simulation (queue discharge
# emerges from car-following); used only to compare measured capacity with HCM.
FOLLOW_UP_MINOR_LEFT_S: Final[float] = 3.3
FOLLOW_UP_MINOR_RIGHT_S: Final[float] = 3.5

# A priority vehicle slower than this is treated as not arriving (it is queued/stopped)
# [m/s]; the HCM "queued" state threshold, 5 mi/h (HCM 6th ed., Ch. 31 queue definition).
V_QUEUED_MPS: Final[float] = 5.0 * 1.609344 / 3.6

# ------------------------------------------------------------- incidents ---------------
# Length of the stationary vehicle that represents an incident (broken-down car) [m];
# equal to the car class length.
INCIDENT_LENGTH_M: Final[float] = 4.5

# ------------------------------------------------------------- stop lines --------------
# Vehicles held at a stop line / lane end come to rest this far before it [m]
# (front bumper to line). Needed so that IDM's asymptotic approach to its rest point can
# never creep over a closed line; the order of 1 m matches typical stopping positions
# behind stop lines. The commitment distance includes it (see engine/gates.py), which
# makes "never cross a closed gate" hold by construction.
STOP_LINE_STANDOFF_M: Final[float] = 1.0

# ---------------------------------------------------------------- signals --------------
# Intergreen from the ITE formulas (ITE, "Determining Vehicle Signal Change and
# Clearance Intervals", 1994/2020):
#   amber   Y  = t_pr + v / (2·a_d)            (level approach)
#   all-red AR = (W + L) / v                   (W: width to clear, L: vehicle length)
# with v the approach speed limit and W the junction-box extent along the approach.
PERCEPTION_REACTION_S: Final[float] = 1.0  # ITE t_pr
ITE_DECEL_MPS2: Final[float] = 3.05  # ITE comfortable deceleration, 10 ft/s²
CLEARANCE_VEHICLE_LENGTH_M: Final[float] = 4.5  # design vehicle for AR: a car

# Lost time per phase = l1 + (amber + all-red) − e. The start-up lost time l1 is MEASURED
# (engine/calibration.py; HCM's default of 2 s is no longer used). The extension of
# effective green e is not measured; it keeps the HCM 6th ed. (Ch. 19) default.
GREEN_EXTENSION_S: Final[float] = 2.0

# Green-time bounds [s]. Minimum green: common practice 5–10 s for vehicle phases
# without pedestrian timing (e.g. FHWA Signal Timing Manual, 2nd ed., Table 5-3).
# Maximum green for max-pressure, and maximum Webster cycle (IRC:93-1985 recommends
# keeping cycles at or below 120 s).
G_MIN_S: Final[float] = 7.0
# Second max-pressure variant ("max_pressure_threshold"): minimum green at the upper end
# of the same 5-15 s range. Its other parameter (the switching threshold) is DERIVED,
# not chosen: see engine/signals.py. Both were fixed before any controller comparison.
G_MIN_THRESHOLD_S: Final[float] = 15.0
G_MAX_S: Final[float] = 60.0
C_MAX_S: Final[float] = 120.0

# Saturation-flow calibration (measured in the simulation, not assumed): a standing
# queue of this many vehicles is released at the line; headways of vehicles after the
# 4th (HCM 6th ed., Ch. 31) are averaged.
SAT_QUEUE_VEHICLES: Final[int] = 24
SAT_SKIP_VEHICLES: Final[int] = 4
CALIBRATION_SEED: Final[int] = 0

# ------------------------------------------------------------------- KPIs --------------
# Detector flow is the crossing count over this window scaled to veh/h [s]; one vehicle
# in the window is 3600 / 60 = 60 veh/h, which the UI states.
DETECTOR_WINDOW_S: Final[float] = 60.0
# Detectors stay this far from road ends [m]: a step moves a vehicle at most
# v_max * DT = 1.7 m, so no step can carry a vehicle across a boundary and the line at once.
DETECTOR_MIN_END_CLEARANCE_M: Final[float] = 20.0
# "Recent" window for mean delay [s]: the 5-minute analysis interval conventional for
# flow rates (HCM uses 15-minute analysis periods with 5-minute peak flow rates).
KPI_RECENT_WINDOW_S: Final[float] = 300.0
# Queues are sampled at this interval and their maximum is kept over the detector window [s].
QUEUE_SAMPLE_PERIOD_S: Final[float] = 1.0
