"""Imperative helper for assembling a ``Network`` by hand.

Lane centrelines are derived from a road's reference line (median side, pointing in the
direction of travel) by exact lateral offsets: lane k sits at
``inner + sum(widths[k+1:]) + widths[k] / 2`` to the left of the reference (left-hand
traffic, lane 0 = kerb lane). Adjacent centrelines are therefore exactly
``(w_i + w_j) / 2`` apart — no visual scaling anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from trafficsim.network import geometry as geo
from trafficsim.network.types import (
    Annotation,
    Connector,
    Control,
    Junction,
    Lane,
    Movement,
    Network,
    Road,
    RoadKind,
    Zone,
)


def kmh(v: float) -> float:
    return v / 3.6


class NetworkBuilder:
    def __init__(self) -> None:
        self._roads: dict[str, Road] = {}
        self._connectors: list[Connector] = []
        self._junctions: list[Junction] = []
        self._zones: list[Zone] = []
        self._annotations: list[Annotation] = []

    # ------------------------------------------------------------------ roads
    def road(
        self,
        rid: str,
        kind: RoadKind,
        reference: np.ndarray,
        widths: Sequence[float],
        inner_offset: float,
        speed_kmh: float,
        level: int | None = None,
    ) -> Road:
        """``widths`` are listed kerb lane first (index 0) toward the median."""
        if rid in self._roads:
            raise ValueError(f"duplicate road {rid}")
        ref = geo.polyline(reference)
        lanes = []
        for k, w in enumerate(widths):
            offset = inner_offset + float(sum(widths[k + 1 :])) + w / 2.0
            centre = geo.offset_left(ref, offset)
            lanes.append(Lane(f"{rid}:{k}", rid, k, float(w), centre, geo.arc_length(centre)))
        lvl = level if level is not None else (0 if kind == "surface" else 1)
        road = Road(rid, kind, lvl, kmh(speed_kmh), ref, inner_offset, tuple(lanes))
        self._roads[rid] = road
        return road

    def _lane(self, rid: str, idx: int) -> Lane:
        return self._roads[rid].lanes[idx]

    # ------------------------------------------------------------ connectors
    def link(self, from_road: str, from_idx: int, to_road: str, to_idx: int) -> Connector:
        """Zero-length continuation (diverge / merge / lane drop / widening)."""
        a, b = self._lane(from_road, from_idx), self._lane(to_road, to_idx)
        gap = float(np.sqrt(((a.centreline[-1] - b.centreline[0]) ** 2).sum()))
        if gap > 1e-6:
            raise ValueError(f"link {a.id}->{b.id}: endpoints differ by {gap:.3f} m")
        path = np.vstack([a.centreline[-1], b.centreline[0]])
        c = Connector(f"{a.id}>{b.id}", a.id, b.id, "through", None, path, 0.0)
        self._connectors.append(c)
        return c

    def turn(
        self,
        junction_id: str,
        from_road: str,
        from_idx: int,
        to_road: str,
        to_idx: int,
        movement: Movement,
        yields: bool = False,
    ) -> Connector:
        a, b = self._lane(from_road, from_idx), self._lane(to_road, to_idx)
        path = geo.turn_path(
            a.centreline[-1],
            geo.end_heading(a.centreline),
            b.centreline[0],
            geo.start_heading(b.centreline),
        )
        c = Connector(
            f"{a.id}>{b.id}", a.id, b.id, movement, junction_id, path, geo.arc_length(path), yields
        )
        self._connectors.append(c)
        return c

    # ------------------------------------------------------- junctions/zones
    def junction(
        self,
        jid: str,
        control: Control,
        x_range: tuple[float, float],
        y_range: tuple[float, float],
        minor_approach_roads: Sequence[str] = (),
    ) -> Junction:
        conns = [c for c in self._connectors if c.junction_id == jid]
        if not conns:
            raise ValueError(f"junction {jid} has no connectors; add turns first")
        approach = tuple(dict.fromkeys(c.from_lane for c in conns))
        minor = tuple(ln for ln in approach if ln.split(":")[0] in minor_approach_roads)
        (x0, x1), (y0, y1) = x_range, y_range
        poly = np.array([[x0, y0, 0.0], [x1, y0, 0.0], [x1, y1, 0.0], [x0, y1, 0.0]])
        j = Junction(jid, control, poly, tuple(c.id for c in conns), approach, minor)
        self._junctions.append(j)
        return j

    def zone(self, zid: str, entry_road: str, exit_road: str) -> None:
        self._zones.append(Zone(zid, entry_road, exit_road))

    def annotate(self, text: str, x: float, y: float, z: float = 0.0, kind: str = "label") -> None:
        self._annotations.append(Annotation(text, (x, y, z), kind))

    def build(self, drive_side: str = "left", meta: dict[str, float] | None = None) -> Network:
        return Network(
            roads=tuple(self._roads.values()),
            connectors=tuple(self._connectors),
            junctions=tuple(self._junctions),
            zones=tuple(self._zones),
            annotations=tuple(self._annotations),
            drive_side=drive_side,  # type: ignore[arg-type]
            meta=dict(meta or {}),
        )
