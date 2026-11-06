"""Route table and per-vehicle path stepping.

A route is the fastest free-flow sequence of roads from an origin zone's entry road to a
destination zone's exit road (``network.routing.fastest_route``). Along a road, the
lanes that lead onward to the route's next road are the route's *good lanes* there;
a vehicle in any other lane must change lanes before the lane ends (mandatory change).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.network.routing import fastest_route
from trafficsim.network.types import Network

NEXT_NONE = -1  # this lane does not lead toward the route's next road
NEXT_EXIT = -2  # end of route: the vehicle leaves the network at the segment end


@dataclass
class RouteTable:
    roads: list[tuple[str, ...]] = field(default_factory=list)
    od: list[tuple[str, str]] = field(default_factory=list)
    index: dict[tuple[str, str], int] = field(default_factory=dict)
    good: list[list[np.ndarray]] = field(default_factory=list)  # [route][rpos] -> bool/lane

    def add(self, net: Network, lg: LaneGraph, origin: str, dest: str) -> int:
        key = (origin, dest)
        if key in self.index:
            return self.index[key]
        roads = fastest_route(net, origin, dest)
        if roads is None:
            raise ValueError(f"no route from {origin} to {dest}")
        return self.add_explicit(lg, tuple(roads), key)

    def add_explicit(self, lg: LaneGraph, roads: tuple[str, ...], key: tuple[str, str]) -> int:
        """Register a given road sequence (e.g. a two-road calibration route that ends,
        and leaves the network, at the end of its last road)."""
        if key in self.index:
            return self.index[key]
        k = len(self.roads)
        self.roads.append(tuple(roads))
        self.od.append(key)
        self.index[key] = k
        good = []
        for rpos, rid in enumerate(roads):
            segs = lg.road_segs[rid]
            good.append(np.array([next_seg(lg, self, k, rpos, sg) != NEXT_NONE for sg in segs]))
            if not good[-1].any():
                raise ValueError(f"route {key}: no lane of {rid} leads onward")
        self.good.append(good)
        return k


def next_seg(lg: LaneGraph, rt: RouteTable, route: int, rpos: int, seg: int) -> int:
    """Next segment on the path from ``seg`` (on road ``rpos`` of the route)."""
    if lg.is_conn[seg]:
        return int(lg.conn_to[seg])
    roads = rt.roads[route]
    if rpos == len(roads) - 1:
        return NEXT_EXIT
    target = roads[rpos + 1]
    for s2, r2 in zip(lg.succ[seg], lg.succ_road[seg], strict=True):
        if r2 == target:
            return s2
    return NEXT_NONE


def lane_offset_to_good(rt: RouteTable, route: int, rpos: int, lane_index: int) -> int:
    """Signed number of lanes to the nearest good lane (0 if already good).

    Positive = toward higher lane index (toward the median in left-hand traffic).
    Ties prefer the kerb side (lower index).
    """
    good = rt.good[route][rpos]
    if good[lane_index]:
        return 0
    idx = np.flatnonzero(good)
    d = idx - lane_index
    return int(d[np.lexsort((d, np.abs(d)))[0]])


def refresh_lane_cache(vs, lg: LaneGraph, rt: RouteTable, i: int) -> None:
    """Update a vehicle's cached ``off``/``goodbits`` after insertion, transfer or change."""
    seg = int(vs.seg[i])
    if lg.is_conn[seg]:
        vs.off[i], vs.goodbits[i] = 0, 0
        return
    route, rpos = int(vs.route[i]), int(vs.rpos[i])
    vs.off[i] = lane_offset_to_good(rt, route, rpos, int(lg.lane_index[seg]))
    vs.goodbits[i] = int(sum(1 << k for k, g in enumerate(rt.good[route][rpos]) if g))
