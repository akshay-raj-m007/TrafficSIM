"""Vehicle classes (IDM + power parameters) and the struct-of-arrays vehicle state.

IDM values are literature defaults (Treiber & Kesting, "Traffic Flow Dynamics", 2013,
urban ranges); the CAV's shorter time gap follows ACC/CACC field studies (e.g. Milanés &
Shladover 2014, T ≈ 0.6–1.1 s). Power-to-mass ratios [W/kg]:
  * car 48: compact car ~60 kW / ~1250 kg incl. occupants;
  * truck/bus 6: loaded goods vehicle — between the HCM US "typical truck" 200 lb/hp
    (≈ 8.2 W/kg) and loaded Indian trucks (often cited ≈ 4–5 W/kg);
  * two-wheeler 33: 110–125 cc commuter ~6 kW / ~180 kg incl. rider;
  * CAV 48: same vehicle platform as the car.
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
    power_to_mass_w_per_kg: float

    def __post_init__(self) -> None:
        for f in self.__dataclass_fields__:
            if f != "name" and getattr(self, f) <= 0:
                raise ValueError(f"{self.name}.{f} must be positive")


VEHICLE_CLASSES: Final[tuple[VehicleClass, ...]] = (
    VehicleClass("car", 4.5, 1.8, 16.7, 1.2, 1.5, 2.0, 2.0, 48.0),
    VehicleClass("truck_bus", 12.0, 2.5, 13.9, 1.8, 0.7, 1.5, 3.0, 6.0),
    VehicleClass("two_wheeler", 2.0, 0.8, 16.7, 0.9, 2.0, 2.5, 1.0, 33.0),
    VehicleClass("cav", 4.5, 1.8, 16.7, 0.8, 1.5, 2.0, 2.0, 48.0),
)
CLASS_INDEX: Final[dict[str, int]] = {c.name: i for i, c in enumerate(VEHICLE_CLASSES)}
MAX_VEHICLE_LENGTH_M: Final[float] = max(c.length_m for c in VEHICLE_CLASSES)


def _col(attr: str) -> np.ndarray:
    a = np.array([getattr(c, attr) for c in VEHICLE_CLASSES], dtype=np.float64)
    a.setflags(write=False)
    return a


# Per-class parameter vectors, indexed by the vehicle's class index.
LEN = _col("length_m")
WIDTH = _col("width_m")
V0 = _col("v0_mps")
T = _col("T_s")
A = _col("a_mps2")
B = _col("b_mps2")
S0 = _col("s0_m")
P2M = _col("power_to_mass_w_per_kg")

# Field name -> dtype of every per-vehicle array.
FIELDS: Final[dict[str, type]] = {
    "vid": np.int64,  # unique id, never reused
    "cls": np.int8,  # index into VEHICLE_CLASSES
    "seg": np.int32,  # current segment (lane or junction connector)
    "s": np.float64,  # front-bumper position along the segment [m]
    "v": np.float64,  # speed [m/s]
    "acc": np.float64,  # last applied acceleration [m/s²]
    "route": np.int32,  # index into the route table
    "rpos": np.int16,  # index of the current road within the route
    "nxt": np.int32,  # next segment on the path (cached), or a NEXT_* code
    "tail": np.int32,  # previous segment while the rear still overlaps it, else -1
    "off": np.int8,  # signed lanes to the nearest lane leading onward (0: fine) [cached]
    "goodbits": np.int32,  # bit k set if lane k of the current road leads onward [cached]
    "lc_timer": np.float64,  # time since the last lane change [s]
    "t_gen": np.float64,  # time the demand arrived (entered the entry queue) [s]
    "t_ins": np.float64,  # time the vehicle was inserted into the network [s]
}


class VehicleState:
    """All active vehicles as parallel arrays (one row per vehicle).

    One global struct-of-arrays lets car-following run as one vectorised NumPy call
    over every vehicle; per-lane leaders are found by sorting on (segment, s).
    """

    vid: np.ndarray
    cls: np.ndarray
    seg: np.ndarray
    s: np.ndarray
    v: np.ndarray
    acc: np.ndarray
    route: np.ndarray
    rpos: np.ndarray
    nxt: np.ndarray
    tail: np.ndarray
    off: np.ndarray
    goodbits: np.ndarray
    lc_timer: np.ndarray
    t_gen: np.ndarray
    t_ins: np.ndarray

    def __init__(self) -> None:
        for name, dtype in FIELDS.items():
            setattr(self, name, np.zeros(0, dtype=dtype))

    @classmethod
    def empty(cls) -> VehicleState:
        return cls()

    @property
    def n(self) -> int:
        return int(self.vid.shape[0])

    def append(self, **row: float) -> int:
        """Append one vehicle; returns its row index."""
        missing = FIELDS.keys() - row.keys()
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")
        for name, dtype in FIELDS.items():
            setattr(self, name, np.append(getattr(self, name), np.array([row[name]], dtype)))
        return self.n - 1

    def keep(self, mask: np.ndarray) -> None:
        """Drop every vehicle whose mask entry is False."""
        for name in FIELDS:
            setattr(self, name, getattr(self, name)[mask])

    @property
    def length(self) -> np.ndarray:
        return LEN[self.cls]
