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
