"""Lane utilisation: how many vehicles actually use every lane and connector, and why not.

A vehicle "arrives" on a segment (a lane or a junction connector) at the step its front
crosses onto it. An arrival from another lane of the same road is a *lane change*; every
other arrival (insertion, a link or a junction connector) is a *transfer*. Per segment the
report gives arrivals/h of both kinds, the mean number of vehicles on it (occupancy) and its
share of the road's arrivals. A segment is *used* if it has at least ``MIN_ARRIVALS_H``
arrivals per hour or an occupancy of at least ``MIN_OCCUPANCY``; both thresholds were fixed
before any result was looked at (they only separate "carries traffic" from "carries nothing").

For every unused segment the cause is computed, not guessed, from the route table:
  no_demand     no flow's route can reach this lane (no route through the road, or none that
                enters it; for a connector: none through that road-to-road transition)
  dead_lane     routes can enter the lane but no route leaves the road on it (the lane does
                not lead onward for any flow)
  unexplained   routes could use it and it carries nothing: a lane-choice problem to fix
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from trafficsim.engine.loop import Simulation
from trafficsim.engine.scenario import Scenario
from trafficsim.network.types import Network

MIN_ARRIVALS_H = 5.0  # arrivals per hour below which a segment carries (almost) nothing
MIN_OCCUPANCY = 0.05  # mean vehicles on a segment below which it is empty


@dataclass(frozen=True, slots=True)
class SegmentUse:
    id: str
    road: str | None  # None for a junction connector
    transfer_h: float
    lane_change_h: float
    occupancy: float
    share: float  # of the road's arrivals (lanes only)
    demand_h: float  # OD demand whose route uses this road / road-to-road transition
    leads_onward: bool  # some flow's route leaves the road through this lane / connector
    cause: str  # used | no_demand | dead_lane | unexplained

    @property
    def arrivals_h(self) -> float:
        return self.transfer_h + self.lane_change_h

    @property
    def used(self) -> bool:
        return self.arrivals_h >= MIN_ARRIVALS_H or self.occupancy >= MIN_OCCUPANCY


def _route_demand(sim: Simulation, demand) -> tuple[dict, dict, dict, dict, dict]:
    """Per road and per (road, next road): OD demand; the lanes a route leaves by (good) or can
    enter, and the connectors some route uses."""
    rt, lg, net = sim.routes, sim.lg, sim.network
    road_h: dict[str, float] = defaultdict(float)
    pair_h: dict[tuple[str, str], float] = defaultdict(float)
    good_lanes: dict[str, set[int]] = defaultdict(set)
    entered: dict[str, set[int]] = defaultdict(set)
    used_conn: set[int] = set()
    for f in demand:
        if f.veh_per_h <= 0:
            continue
        r = rt.add(net, lg, f.origin, f.destination)
        roads = rt.roads[r]
        for pos, rid in enumerate(roads):
            road_h[rid] += f.veh_per_h
            good = [k for k, g in enumerate(rt.good[r][pos]) if g]
            good_lanes[rid] |= set(good)
            if pos == 0:
                entered[rid] |= set(range(lg.road_segs[rid].__len__()))  # insertion / lane changes
            if pos + 1 < len(roads):
                for a in (lg.road_segs[rid][k] for k in good):
                    for nxt in lg.succ[a]:
                        out = int(lg.conn_to[nxt]) if lg.is_conn[nxt] else nxt
                        if lg.road_of[out] == roads[pos + 1]:
                            entered[roads[pos + 1]].add(int(lg.lane_index[out]))
            if pos + 1 < len(roads):
                pair_h[(rid, roads[pos + 1])] += f.veh_per_h
    for c in net.connectors:
        if c.junction_id is None:
            continue
        ra, rb = net.road_of(c.from_lane).id, net.road_of(c.to_lane).id
        lane = int(net.lane(c.from_lane).index)
        if pair_h.get((ra, rb), 0.0) > 0.0 and lane in good_lanes[ra]:
            used_conn.add(lg.seg_of[c.id])
    return road_h, pair_h, good_lanes, entered, used_conn


def measure(net: Network, scenario: Scenario, warmup_s: float = 300.0) -> list[SegmentUse]:
    """Run ``scenario`` to its end and report every lane and connector (window after warm-up)."""
    if not 0.0 <= warmup_s < scenario.duration_s:
        raise ValueError("warm-up must be inside the run")
    sim = Simulation(net, scenario)
    lg, n = sim.lg, sim.lg.n
    road_ix = {r: i for i, r in enumerate(lg.road_segs)}
    road_of = np.array([-1 if r is None else road_ix[r] for r in lg.road_of])
    transfer, changed, occ = np.zeros(n), np.zeros(n), np.zeros(n)
    last = np.full(1024, -1, dtype=np.int64)  # last segment of each vehicle id
    warm_tick = round(warmup_s * 10)
    while sim.step():
        vs = sim.vehicles
        if vs.n == 0:
            continue
        if int(vs.vid.max()) >= last.size:
            last = np.concatenate([last, np.full(last.size, -1, dtype=np.int64)])
        prev = last[vs.vid]
        last[vs.vid] = vs.seg
        if sim.tick <= warm_tick:
            continue
        occ += np.bincount(vs.seg, minlength=n) * sim.dt
        moved = vs.seg != prev
        lane_change = moved & (prev >= 0) & (road_of[np.maximum(prev, 0)] == road_of[vs.seg])
        lane_change &= road_of[vs.seg] >= 0
        transfer += np.bincount(vs.seg[moved & ~lane_change], minlength=n)
        changed += np.bincount(vs.seg[lane_change], minlength=n)
    seconds = scenario.duration_s - warmup_s
    per_h = 3600.0 / seconds
    road_h, pair_h, good_lanes, entered, used_conn = _route_demand(sim, sim.current_demand)
    totals = {
        rid: sum(transfer[k] + changed[k] for k in segs) for rid, segs in lg.road_segs.items()
    }
    conn_of = {lg.seg_of[c.id]: c for c in net.connectors if c.junction_id is not None}
    out = []
    for k in range(n):
        rid = lg.road_of[k]
        if rid is not None:
            lane_no = int(lg.lane_index[k])
            onward = lane_no in good_lanes.get(rid, set())
            demand = road_h.get(rid, 0.0) if lane_no in entered.get(rid, set()) else 0.0
            share = (transfer[k] + changed[k]) / totals[rid] if totals[rid] else 0.0
        else:
            c = conn_of[k]
            ra, rb = net.road_of(c.from_lane).id, net.road_of(c.to_lane).id
            demand, onward, share = pair_h.get((ra, rb), 0.0), k in used_conn, 0.0
        s = SegmentUse(lg.ids[k], rid, transfer[k] * per_h, changed[k] * per_h,
                       occ[k] / seconds, share, demand, onward, "used")  # fmt: skip
        cause = "used" if s.used else (
            "no_demand" if demand <= 0.0 else ("dead_lane" if not onward else "unexplained")
        )  # fmt: skip
        out.append(SegmentUse(s.id, s.road, s.transfer_h, s.lane_change_h, s.occupancy, share,
                              demand, onward, cause))  # fmt: skip
    return out
