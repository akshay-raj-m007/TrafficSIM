"""Structural settings of the demo network: the lane groups and widths a user can change.

Two main lane groups meet at the diverge:
  * the SURFACE group (``surface_lanes`` per direction, ``surface_width_m``): the road through J1;
  * the FLYOVER / through group (``flyover_lanes``, ``flyover_width_m``): the ramps, the deck,
    the flyover lanes of the section east of the merge, and J2's major road.
East of J1 the surface group continues as the link lanes (same count, width and position), which
join the flyover lanes at the merge and end at the lane drop. The cross street (3.25 m) and J2's
minor road (2.75 m) keep their widths. The west
arterial therefore has surface + flyover lanes per direction. The default (2 + 2 lanes, 3.5 m)
is the original demo network, reproduced exactly.

Ranges (checked with a message, never clamped): 1-4 lanes per group; lane width 2.5-4.0 m.
2.5 m is the width of the widest vehicle (truck / bus, engine/vehicle.py); 4.0 m is above the
usual 3.5-3.75 m design widths. Below 3.05 m the lane-width speed model extrapolates (it is
already used by the 2.75 m minor road).
"""

from __future__ import annotations

from dataclasses import dataclass

LANES_RANGE = (1, 4)
WIDTH_RANGE_M = (2.5, 4.0)
J2_MINOR_LANES = (1, 2)


def check_lanes(name: str, value, lo: int, hi: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValueError(f"{name} {value!r} is outside {lo}..{hi} (whole lanes)")
    return value


def check_width(name: str, value) -> float:
    lo, hi = WIDTH_RANGE_M
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{name} {value!r} is not a number")
    if not lo <= value <= hi:
        raise ValueError(f"{name} {value} m is outside {lo}..{hi} m")
    return value


@dataclass(frozen=True, slots=True)
class Structure:
    j2_minor_lanes: int = 2  # 1 shared lane or 2 turn lanes on J2's minor approach
    surface_lanes: int = 2
    flyover_lanes: int = 2
    surface_width_m: float = 3.5
    flyover_width_m: float = 3.5

    def __post_init__(self) -> None:
        check_lanes("j2_minor_lanes", self.j2_minor_lanes, *J2_MINOR_LANES)
        check_lanes("surface_lanes", self.surface_lanes, *LANES_RANGE)
        check_lanes("flyover_lanes", self.flyover_lanes, *LANES_RANGE)
        check_width("surface_width_m", self.surface_width_m)
        check_width("flyover_width_m", self.flyover_width_m)

    @property
    def is_default(self) -> bool:
        return self == Structure()
