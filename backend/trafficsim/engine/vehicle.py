"""Vehicle classes (IDM parameters) and the struct-of-arrays vehicle state.

Parameter values are *provisional literature defaults* (Treiber & Kesting, "Traffic
Flow Dynamics", 2013, urban IDM ranges; shorter CAV time gap per ACC/CACC studies).
They are reviewed and documented in step 2 before any result is reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np


@dataclass(frozen=True, slots=True)
class VehicleClass:
    name: str
    length_m: float  # bumper to bumper
    width_m: float
    v0_mps: float  # desired speed on an unrestricted road
    T_s: float  # desired time gap
    a_mps2: float  # maximum acceleration
    b_mps2: float  # comfortable deceleration
    s0_m: float  # minimum standstill gap

    def __post_init__(self) -> None:
        for field in ("length_m", "width_m", "v0_mps", "T_s", "a_mps2", "b_mps2", "s0_m"):
            if getattr(self, field) <= 0:
                raise ValueError(f"{self.name}.{field} must be positive")


VEHICLE_CLASSES: Final[tuple[VehicleClass, ...]] = (
    VehicleClass("car", 4.5, 1.8, 16.7, 1.2, 1.5, 2.0, 2.0),
    VehicleClass("truck_bus", 12.0, 2.5, 13.9, 1.8, 0.7, 1.5, 3.0),
    VehicleClass("two_wheeler", 2.0, 0.8, 16.7, 0.9, 2.0, 2.5, 1.0),
    VehicleClass("cav", 4.5, 1.8, 16.7, 0.8, 1.5, 2.0, 2.0),
)
CLASS_INDEX: Final[dict[str, int]] = {c.name: i for i, c in enumerate(VEHICLE_CLASSES)}


@dataclass(slots=True)
class VehicleState:
    """All active vehicles as parallel arrays (one row per vehicle).

    A single global struct-of-arrays (rather than one array set per lane) lets the
    car-following update run as one vectorised NumPy call over every vehicle; per-lane
    leader lookup is done by sorting on (lane, s).
    """

    vid: np.ndarray  # int64, unique id, never reused
    cls: np.ndarray  # int8, index into VEHICLE_CLASSES
    lane: np.ndarray  # int32, index into Network.lane_ids
    s: np.ndarray  # float64, position along lane [m]
    v: np.ndarray  # float64, speed [m/s]
    acc: np.ndarray  # float64, last applied acceleration [m/s^2]

    @classmethod
    def empty(cls) -> VehicleState:
        return cls(
            vid=np.zeros(0, dtype=np.int64),
            cls=np.zeros(0, dtype=np.int8),
            lane=np.zeros(0, dtype=np.int32),
            s=np.zeros(0, dtype=np.float64),
            v=np.zeros(0, dtype=np.float64),
            acc=np.zeros(0, dtype=np.float64),
        )

    @property
    def n(self) -> int:
        return int(self.vid.shape[0])
