"""Demand: Poisson arrivals per entry zone → FIFO entry queues → safe insertion.

Each origin zone generates arrivals at rate λ = Σ OD flows from it, with exponential
headways drawn from the ``spawn`` stream. Each arrival's class comes from the
``vehicle_class`` stream (scenario mix) and its destination from the ``route`` stream
(proportional to the OD flows). Arrivals join the zone's entry queue; a queued vehicle
is inserted only when the insertion rule (params/driving.py) is satisfied, otherwise it
waits — counted as unserved demand, never dropped.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.rng import RngStreams
from trafficsim.engine.routes import RouteTable, next_seg
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import CLASS_INDEX, LEN, S0, T, VehicleState
from trafficsim.network.types import Network

SECONDS_PER_HOUR = 3600.0


@dataclass
class Queued:
    t_gen: float
    cls: int
    route: int


@dataclass
class _Zone:
    entry_road: str
    rate_vps: float
    routes: np.ndarray  # route index per destination
    cum_p: np.ndarray  # cumulative destination probabilities
    next_t: float
    queue: deque[Queued]


class Demand:
    def __init__(
        self, net: Network, lg: LaneGraph, rt: RouteTable, sc: Scenario, rng: RngStreams
    ) -> None:
        self.lg, self.rt, self.rng = lg, rt, rng
        self.cls_idx = np.array([CLASS_INDEX[n] for n, _ in sc.vehicle_mix])
        self.cls_cum = np.cumsum([p for _, p in sc.vehicle_mix])
        self.zones: list[_Zone] = []
        for z in net.zones:  # network order: deterministic
            flows = [f for f in sc.demand if f.origin == z.id and f.veh_per_h > 0]
            if not flows:
                continue
            rate = sum(f.veh_per_h for f in flows) / SECONDS_PER_HOUR
            routes = np.array([rt.add(net, lg, f.origin, f.destination) for f in flows])
            cum = np.cumsum([f.veh_per_h for f in flows]) / (rate * SECONDS_PER_HOUR)
            first = float(rng.spawn.exponential(1.0 / rate))
            self.zones.append(_Zone(z.entry_road, rate, routes, cum, first, deque()))
        self.generated = 0
        self.inserted = 0
        self.next_vid = 0

    @property
    def queued(self) -> int:
        return sum(len(z.queue) for z in self.zones)

    def queued_by_zone(self) -> dict[str, int]:
        return {z.entry_road: len(z.queue) for z in self.zones}

    def generate(self, t_now: float) -> None:
        """Move every arrival with arrival time <= t_now into its zone's queue."""
        for z in self.zones:
            while z.next_t <= t_now:
                u_cls = self.rng.vehicle_class.random()
                cls = int(self.cls_idx[np.searchsorted(self.cls_cum, u_cls, side="right")])
                u_dst = self.rng.route.random()
                route = int(z.routes[np.searchsorted(z.cum_p, u_dst, side="right")])
                z.queue.append(Queued(z.next_t, cls, route))
                self.generated += 1
                z.next_t += float(self.rng.spawn.exponential(1.0 / z.rate_vps))

    def insert(self, vs: VehicleState, t_now: float) -> None:
        """Insert queue heads where the insertion rule allows (≤ 1 per lane per step)."""
        for z in self.zones:
            segs = self.lg.road_segs[z.entry_road]
            used: set[int] = set()
            while z.queue:
                q = z.queue[0]
                choice = self._best_lane(vs, segs, q, used)
                if choice is None:
                    break
                k, s_front, v_ins = choice
                used.add(k)
                z.queue.popleft()
                self._append(vs, q, segs[k], s_front, v_ins, t_now)

    def _best_lane(self, vs, segs, q: Queued, used: set[int]):
        good = self.rt.good[q.route][0]
        L, s0, tg = LEN[q.cls], S0[q.cls], T[q.cls]
        best = None
        for k, sg in enumerate(segs):
            if k in used or not good[k]:
                continue
            v_des = float(self.lg.v0_eff[sg, q.cls])
            on = np.flatnonzero(vs.seg == sg)
            if on.size == 0:
                gap, v_ins = np.inf, v_des
            else:
                j = on[np.argmin(vs.s[on])]
                gap = float(vs.s[j] - LEN[vs.cls[j]] - L)  # front of new vehicle at s = L
                if gap < s0:
                    continue
                v_ins = min(v_des, float(vs.v[j]), (gap - s0) / tg)
            if best is None or gap > best[0]:
                best = (gap, k, float(L), v_ins)
        return None if best is None else best[1:]

    def _append(self, vs, q: Queued, seg: int, s_front: float, v: float, t_now: float):
        nxt = next_seg(self.lg, self.rt, q.route, 0, seg)
        vs.append(
            vid=self.next_vid, cls=q.cls, seg=seg, s=s_front, v=v, acc=0.0, route=q.route,
            rpos=0, nxt=nxt, tail=-1, lc_timer=0.0, t_gen=q.t_gen, t_ins=t_now,
        )  # fmt: skip
        self.next_vid += 1
        self.inserted += 1
        return self.next_vid - 1

    def place(self, vs, route: int, cls: int, seg: int, s: float, v: float, t_now: float):
        """Scripted insertion (tests/experiments); counted as generated and inserted."""
        self.generated += 1
        return self._append(vs, Queued(t_now, cls, route), seg, s, v, t_now)
