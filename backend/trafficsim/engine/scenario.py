"""Scenario definition: everything that, together with the network, fixes a run.

``dt`` is deliberately *not* a field — the time step is a global constant
(see ``constants.DT``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from trafficsim.engine.constants import ticks_for
from trafficsim.engine.vehicle import CLASS_INDEX

# "uncontrolled": no signals at J1 (calibration experiments only).
SignalControl = Literal["fixed_webster", "max_pressure", "uncontrolled"]


@dataclass(frozen=True, slots=True)
class OdFlow:
    """Demand from one origin zone to one destination zone [veh/h]."""

    origin: str
    destination: str
    veh_per_h: float

    def __post_init__(self) -> None:
        if self.veh_per_h < 0:
            raise ValueError("demand must be non-negative")
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")


@dataclass(frozen=True, slots=True)
class Incident:
    """A stationary vehicle (breakdown) at a lane position for a time window."""

    lane_id: str
    s_m: float  # front position of the stopped vehicle along the lane [m]
    t_start_s: float
    duration_s: float

    def __post_init__(self) -> None:
        if self.s_m <= 0 or self.duration_s <= 0 or self.t_start_s < 0:
            raise ValueError("incident needs s > 0, duration > 0, start >= 0")

    def active(self, t: float) -> bool:
        return self.t_start_s <= t < self.t_start_s + self.duration_s


DEFAULT_MIX: tuple[tuple[str, float], ...] = (
    ("car", 0.55),
    ("truck_bus", 0.10),
    ("two_wheeler", 0.30),
    ("cav", 0.05),
)


@dataclass(frozen=True, slots=True)
class Scenario:
    seed: int = 42
    duration_s: float = 3600.0
    demand: tuple[OdFlow, ...] = ()
    vehicle_mix: tuple[tuple[str, float], ...] = field(default=DEFAULT_MIX)
    signal_control: SignalControl = "fixed_webster"
    incidents: tuple[Incident, ...] = ()

    def __post_init__(self) -> None:
        ticks_for(self.duration_s)  # validates multiple of DT
        names = [n for n, _ in self.vehicle_mix]
        unknown = [n for n in names if n not in CLASS_INDEX]
        if unknown:
            raise ValueError(f"unknown vehicle classes in mix: {unknown}")
        if len(set(names)) != len(names):
            raise ValueError("duplicate class in vehicle mix")
        shares = [s for _, s in self.vehicle_mix]
        if any(s < 0 for s in shares) or abs(sum(shares) - 1.0) > 1e-9:
            raise ValueError("vehicle mix shares must be non-negative and sum to 1")
        if self.signal_control not in ("fixed_webster", "max_pressure", "uncontrolled"):
            raise ValueError(f"unknown signal control {self.signal_control!r}")

    @property
    def total_ticks(self) -> int:
        return ticks_for(self.duration_s)
