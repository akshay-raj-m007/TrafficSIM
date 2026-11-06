"""Run a scenario once and check, at EVERY step, what the hard invariants need.

Collision checking is independent of the engine's leader search: all vehicle bodies
(plus tails still overlapping the previous segment) are sorted per segment and every
consecutive pair must have rear(ahead) − front(behind) > 0; inside junctions no two
vehicles on conflicting connectors may cover their conflict point at the same time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from trafficsim.engine.loop import Simulation
from trafficsim.engine.vehicle import LEN
from trafficsim.network.conflicts import conflict_table


@dataclass
class Report:
    sim: Simulation
    hashes: list[str] = field(default_factory=list)
    min_gap: float = np.inf
    min_speed: float = np.inf
    conflict_overlaps: list[tuple[float, str, str]] = field(default_factory=list)
    conservation_errors: list[str] = field(default_factory=list)
    transitions: set[tuple[int, int]] = field(default_factory=set)
    peak_vehicles: int = 0


def _state_hash(sim: Simulation) -> str:
    vs = sim.vehicles
    h = hashlib.sha256()
    for a in (vs.vid, vs.seg, vs.s, vs.v, vs.route, vs.tail):
        h.update(np.ascontiguousarray(a).tobytes())
    h.update(str((sim.demand.generated, sim.exited, sim.demand.queued)).encode())
    return h.hexdigest()


def _min_body_gap(sim: Simulation) -> float:
    vs, lg = sim.vehicles, sim.lg
    if vs.n < 2:
        return np.inf
    lens = LEN[vs.cls]
    g = np.flatnonzero(vs.tail >= 0)
    seg = np.concatenate([vs.seg, vs.tail[g]])
    front = np.concatenate([vs.s, lg.length[vs.tail[g]] + vs.s[g]])
    rear = front - np.concatenate([lens, lens[g]])
    o = np.lexsort((front, seg))
    same = seg[o][1:] == seg[o][:-1]
    gaps = rear[o][1:] - front[o][:-1]
    return float(gaps[same].min()) if np.any(same) else np.inf


def run_checked(net, scenario, steps: int) -> Report:
    sim = Simulation(net, scenario)
    lg = sim.lg
    table = conflict_table(net)
    pairs = [(lg.seg_of[a], lg.seg_of[b], cf.s_self, cf.s_other)
             for a, row in table.items() for b, cf in row.items() if a < b]  # fmt: skip
    rep = Report(sim)
    prev: dict[int, int] = {}
    for _ in range(steps):
        sim.step()
        vs = sim.vehicles
        rep.hashes.append(_state_hash(sim))
        rep.min_gap = min(rep.min_gap, _min_body_gap(sim))
        if vs.n:
            rep.min_speed = min(rep.min_speed, float(vs.v.min()))
        rep.peak_vehicles = max(rep.peak_vehicles, vs.n)
        d = sim.demand
        if (
            d.generated != sim.active + sim.exited + d.queued
            or d.inserted != sim.active + sim.exited
        ):
            rep.conservation_errors.append(f"t={sim.time_s}")
        if len(set(vs.vid.tolist())) != vs.n:
            rep.conservation_errors.append(f"duplicate vid at t={sim.time_s}")
        rear = vs.s - LEN[vs.cls]
        tail_rear = np.where(vs.tail >= 0, lg.length[np.maximum(vs.tail, 0)] + rear, np.inf)
        for a, b, sa, sb in pairs:
            on_a = ((vs.seg == a) & (rear <= sa) & (vs.s >= sa)) | (
                (vs.tail == a) & (tail_rear <= sa)
            )
            on_b = ((vs.seg == b) & (rear <= sb) & (vs.s >= sb)) | (
                (vs.tail == b) & (tail_rear <= sb)
            )
            if on_a.any() and on_b.any():
                rep.conflict_overlaps.append((sim.time_s, lg.ids[a], lg.ids[b]))
        cur = dict(zip(vs.vid.tolist(), vs.seg.tolist(), strict=True))
        for vid, sg in cur.items():
            p = prev.get(vid)
            if p is not None and p != sg:
                rep.transitions.add((p, sg))
        prev = cur
    return rep
