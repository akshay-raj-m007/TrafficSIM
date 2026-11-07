"""Structural settings of the demo network: the lane groups and widths a user can change.

Two main lane groups meet at the diverge:
  * the SURFACE group (``surface_lanes`` per direction, ``surface_width_m``): the road through J1;
  * the FLYOVER / through group (``flyover_lanes``, ``flyover_width_m``): the ramps, the deck,
    the section east of the merge (the flyover lanes plus the single J1 link lane, which ends
    at the lane drop) and J2's major road.
The J1 link lane (3.0 m), the cross street (3.25 m) and J2's minor road (2.75 m) keep their
widths. The west arterial therefore has surface + flyover lanes per direction. The default
(2 + 2 lanes, 3.5 m) is the original demo network, reproduced exactly.

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


@dataclass(frozen=True, slots=True)
class Structure:
    j2_minor_lanes: int = 2  # 1 shared lane or 2 turn lanes on J2's minor approach
    surface_lanes: int = 2
    flyover_lanes: int = 2
    surface_width_m: float = 3.5
    flyover_width_m: float = 3.5

    def __post_init__(self) -> None:
        for name, value, (lo, hi) in (
            ("j2_minor_lanes", self.j2_minor_lanes, J2_MINOR_LANES),
            ("surface_lanes", self.surface_lanes, LANES_RANGE),
            ("flyover_lanes", self.flyover_lanes, LANES_RANGE),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
                raise ValueError(f"{name} {value!r} is outside {lo}..{hi} (whole lanes)")
        lo_w, hi_w = WIDTH_RANGE_M
        for name, value in (
            ("surface_width_m", self.surface_width_m),
            ("flyover_width_m", self.flyover_width_m),
        ):
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"{name} {value!r} is not a number")
            if not lo_w <= value <= hi_w:
                raise ValueError(f"{name} {value} m is outside {lo_w}..{hi_w} m")

    @property
    def is_default(self) -> bool:
        return self == Structure()
