"""Static road-network types. All lengths in metres; axes x east, y north, z up.

Left-hand traffic: lane index 0 is the kerb lane (leftmost in the direction of travel),
higher indices are toward the median. Arrays are made read-only on construction so the
frozen dataclasses really are immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

RoadKind = Literal["surface", "flyover", "ramp"]
Control = Literal["signalised", "give_way"]
Movement = Literal["through", "left", "right"]


def _frozen(arr: np.ndarray) -> np.ndarray:
    out = np.array(arr, dtype=np.float64, copy=True)
    if out.ndim != 2 or out.shape[1] != 3 or out.shape[0] < 2:
        raise ValueError(f"polyline must be (N>=2, 3), got {out.shape}")
    out.setflags(write=False)
    return out


@dataclass(frozen=True, eq=False, slots=True)
class Lane:
    id: str
    road_id: str
    index: int  # 0 = kerb lane
    width_m: float
    centreline: np.ndarray  # (N, 3)
    length_m: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "centreline", _frozen(self.centreline))
        if self.width_m <= 0 or self.length_m <= 0:
            raise ValueError(f"lane {self.id}: width and length must be positive")


@dataclass(frozen=True, eq=False, slots=True)
class Road:
    id: str
    kind: RoadKind
    level: int  # 0 = ground, 1 = grade-separated (flyover deck and its ramps)
    speed_limit_mps: float
    reference: np.ndarray  # (N, 3) median-side reference line, direction of travel
    inner_offset_m: float  # gap between reference line and the median-side lane edge
    lanes: tuple[Lane, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _frozen(self.reference))
        if [ln.index for ln in self.lanes] != list(range(len(self.lanes))):
            raise ValueError(f"road {self.id}: lane indices must be 0..n-1")

    @property
    def length_m(self) -> float:
        return self.lanes[0].length_m

    @property
    def n_lanes(self) -> int:
        return len(self.lanes)


@dataclass(frozen=True, eq=False, slots=True)
class Connector:
    """A permitted lane-to-lane transition.

    Inside a junction (``junction_id`` set) it is a turn path with real length.
    Outside junctions (diverge, merge, lane drop, widening) it joins two lanes whose
    end/start points coincide, so its path has zero length.
    """

    id: str
    from_lane: str
    to_lane: str
    movement: Movement
    junction_id: str | None
    path: np.ndarray  # (N, 3)
    length_m: float
    yields: bool = False  # must give way (minor approach / opposed turn)

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _frozen(self.path))


@dataclass(frozen=True, eq=False, slots=True)
class Junction:
    id: str
    control: Control
    polygon: np.ndarray  # (K, 3) outline of the junction area, z = surface level
    connector_ids: tuple[str, ...]
    approach_lanes: tuple[str, ...]  # lanes that end at the junction's stop/yield line
    minor_approach_lanes: tuple[str, ...] = ()  # give-way approaches

    def __post_init__(self) -> None:
        poly = np.array(self.polygon, dtype=np.float64, copy=True)
        poly.setflags(write=False)
        object.__setattr__(self, "polygon", poly)


@dataclass(frozen=True, slots=True)
class Zone:
    """An origin/destination at the network boundary."""

    id: str
    entry_road: str  # vehicles are spawned at the start of this road
    exit_road: str  # vehicles leave at the end of this road


@dataclass(frozen=True, slots=True)
class Annotation:
    text: str
    position: tuple[float, float, float]
    kind: str = "label"


@dataclass(frozen=True, eq=False, slots=True)
class Network:
    roads: tuple[Road, ...]
    connectors: tuple[Connector, ...]
    junctions: tuple[Junction, ...]
    zones: tuple[Zone, ...]
    annotations: tuple[Annotation, ...] = ()
    drive_side: Literal["left", "right"] = "left"
    meta: dict[str, float] = field(default_factory=dict)  # structural constants (deck z, ...)
    _road: dict[str, Road] = field(default_factory=dict, init=False, repr=False)
    _lane: dict[str, Lane] = field(default_factory=dict, init=False, repr=False)
    _out: dict[str, tuple[Connector, ...]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._road.update({r.id: r for r in self.roads})
        self._lane.update({ln.id: ln for r in self.roads for ln in r.lanes})
        if len(self._road) != len(self.roads) or len(self._lane) != sum(
            r.n_lanes for r in self.roads
        ):
            raise ValueError("duplicate road or lane id")
        out: dict[str, list[Connector]] = {}
        for c in self.connectors:
            if c.from_lane not in self._lane or c.to_lane not in self._lane:
                raise ValueError(f"connector {c.id} references unknown lane")
            out.setdefault(c.from_lane, []).append(c)
        self._out.update({k: tuple(v) for k, v in out.items()})

    def road(self, road_id: str) -> Road:
        return self._road[road_id]

    def lane(self, lane_id: str) -> Lane:
        return self._lane[lane_id]

    def road_of(self, lane_id: str) -> Road:
        return self._road[self._lane[lane_id].road_id]

    def successors(self, lane_id: str) -> tuple[Connector, ...]:
        return self._out.get(lane_id, ())

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(self._lane)

    def zone(self, zone_id: str) -> Zone:
        return next(z for z in self.zones if z.id == zone_id)
