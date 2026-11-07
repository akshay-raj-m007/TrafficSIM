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
from trafficsim.engine.routes import RouteTable, next_seg, refresh_lane_cache
from trafficsim.engine.scenario import OdFlow, Scenario
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
    zone_id: str
    entry_road: str
    rate_vps: float
    routes: np.ndarray  # route index per destination
    cum_p: np.ndarray  # cumulative destination probabilities
    next_t: float
    queue: deque[Queued]
    flows: tuple = ()  # the OdFlows currently in force from this zone
    ever_active: bool = False


class Demand:
    def __init__(
        self, net: Network, lg: LaneGraph, rt: RouteTable, sc: Scenario, rng: RngStreams
    ) -> None:
        self.net, self.lg, self.rt, self.rng = net, lg, rt, rng
        self.set_mix(sc.vehicle_mix)
        # Every zone exists (rate 0 until it has demand) so demand can change live. A zone
        # without flows draws nothing, so runs without live changes are unchanged.
        self.zones: list[_Zone] = [
            _Zone(z.id, z.entry_road, 0.0, np.array([], dtype=int), np.array([]), np.inf, deque())
            for z in net.zones  # network order: deterministic
        ]
        self.set_demand(sc.demand, 0.0)
        self.generated = 0
        self.inserted = 0
        self.next_vid = 0

    def set_mix(self, mix: tuple[tuple[str, float], ...]) -> None:
        """Class shares for arrivals from now on (the scenario validates the shares)."""
        self.cls_idx = np.array([CLASS_INDEX[n] for n, _ in mix])
        self.cls_cum = np.cumsum([p for _, p in mix])

    def set_demand(self, flows: tuple[OdFlow, ...], t_now: float) -> None:
        """Replace the whole OD demand. A zone whose total rate changes redraws its next
        arrival as ``t_now + Exp(new rate)`` from the spawn stream (valid because the
        exponential is memoryless); a zone whose rate is unchanged keeps its next arrival."""
        zone_ids = {z.zone_id for z in self.zones}
        for f in flows:
            if f.origin not in zone_ids or f.destination not in zone_ids:
                raise ValueError(f"demand {f.origin}->{f.destination}: unknown zone")
        for z in self.zones:
            z.flows = tuple(f for f in flows if f.origin == z.zone_id and f.veh_per_h > 0)
            rate = sum(f.veh_per_h for f in z.flows) / SECONDS_PER_HOUR
            changed = rate != z.rate_vps
            z.rate_vps = rate
            self.refresh_routes(z)
            if changed:
                z.next_t = (
                    t_now + float(self.rng.spawn.exponential(1.0 / rate)) if rate > 0 else np.inf
                )
            z.ever_active = z.ever_active or rate > 0

    def refresh_routes(self, z: _Zone | None = None) -> None:
        """(Re)assign each zone's destination routes from the route table's current closures."""
        for zz in [z] if z else self.zones:
            if not zz.flows:
                zz.routes, zz.cum_p = np.array([], dtype=int), np.array([])
                continue
            zz.routes = np.array(
                [self.rt.add(self.net, self.lg, f.origin, f.destination) for f in zz.flows]
            )
            zz.cum_p = np.cumsum([f.veh_per_h for f in zz.flows]) / (zz.rate_vps * SECONDS_PER_HOUR)

    def remap_queued(self) -> None:
        """Entry-queue vehicles take the route table's current routes (after a closure)."""
        for z in self.zones:
            for q in z.queue:
                origin, dest = self.rt.od[q.route][:2]
                q.route = self.rt.add(self.net, self.lg, origin, dest)

    def class_indices(self) -> list[int]:
        """Indices of the vehicle classes that can occur (positive share in the mix)."""
        shares = np.diff(np.concatenate([[0.0], self.cls_cum]))
        return [int(c) for c, s in zip(self.cls_idx, shares, strict=True) if s > 0]

    @property
    def queued(self) -> int:
        return sum(len(z.queue) for z in self.zones)

    def queued_by_zone(self) -> dict[str, int]:
        return {z.entry_road: len(z.queue) for z in self.zones if z.ever_active or z.queue}

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

    def _append(self, vs, q: Queued, seg: int, s_front: float, v: float, t_now: float, rpos=0):
        nxt = next_seg(self.lg, self.rt, q.route, rpos, seg)
        vs.append(
            vid=self.next_vid, cls=q.cls, seg=seg, s=s_front, v=v, acc=0.0, route=q.route,
            rpos=rpos, nxt=nxt, tail=-1, off=0, goodbits=0, lc_timer=0.0, t_gen=q.t_gen,
            t_ins=t_now,
        )  # fmt: skip
        refresh_lane_cache(vs, self.lg, self.rt, vs.n - 1)
        self.next_vid += 1
        self.inserted += 1
        return self.next_vid - 1

    def insert_now(self, vs, route: int, cls: int, t_now: float) -> int | None:
        """Insert one vehicle on the route's entry road with the regular insertion rule
        (lane choice, gap, insertion speed), bypassing the arrival process and entry queue.
        Returns the vehicle id, or None if the rule does not allow it right now."""
        q = Queued(t_now, cls, route)
        segs = self.lg.road_segs[self.rt.roads[route][0]]
        choice = self._best_lane(vs, segs, q, set())
        if choice is None:
            return None
        k, s_front, v_ins = choice
        self.generated += 1
        return self._append(vs, q, segs[k], s_front, v_ins, t_now)

    def place(self, vs, route: int, cls: int, seg: int, s: float, v: float, t_now: float,
              rpos: int = 0):  # fmt: skip
        """Scripted insertion (tests/experiments); counted as generated and inserted."""
        self.generated += 1
        return self._append(vs, Queued(t_now, cls, route), seg, s, v, t_now, rpos)
