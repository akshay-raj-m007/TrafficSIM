"""Fixed-time plan from Webster's formula, with every input derived, none assumed.

phases       one per approach (approach-wise split phasing)
intergreen   ITE amber t_pr + v/(2a) and all-red (W + L)/v from junction geometry
lost time    per phase l1 + intergreen − e; l1 is the MEASURED start-up loss (flow-weighted
             over the phase's movements), e = 2 s is the HCM default (not measured)
flows        OD demand routed through the junction; a movement served from several
             lanes is split equally between them
y            per lane Σ q_m / s_m with s_m the *measured* saturation flow of each
             movement (engine/calibration.py); phase y = max over its lanes
cycle        C0 = (1.5 L + 5) / (1 − Y), bounded below by the minimum feasible cycle
             Σ(G_MIN + intergreen) and above by C_MAX; Y ≥ 1 → C_MAX, flagged
greens       effective green g ∝ y; displayed G = g + l1 − e, at least G_MIN, so that
             C = Σ (G + intergreen) exactly
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafficsim.engine.params.control import (
    C_MAX_S,
    CLEARANCE_VEHICLE_LENGTH_M,
    G_MIN_S,
    GREEN_EXTENSION_S,
    ITE_DECEL_MPS2,
    PERCEPTION_REACTION_S,
)
from trafficsim.network.types import Junction, Network


@dataclass(frozen=True)
class Phase:
    approach_road: str
    connector_ids: tuple[str, ...]
    amber_s: float
    all_red_s: float

    @property
    def intergreen_s(self) -> float:
        return self.amber_s + self.all_red_s


@dataclass(frozen=True)
class WebsterPlan:
    cycle_s: float
    greens_s: tuple[float, ...]
    y: tuple[float, ...]
    Y: float
    lost_s: float
    c0_s: float  # unbounded Webster optimum (inf if Y >= 1)
    oversaturated: bool
    startup_lost_s: tuple[float, ...] = ()  # measured l1 per phase


def build_phases(net: Network, j: Junction) -> list[Phase]:
    conns = [c for c in net.connectors if c.junction_id == j.id]
    (x0, y0), (x1, y1) = j.polygon[:, :2].min(0), j.polygon[:, :2].max(0)
    phases = []
    for road in dict.fromkeys(net.lane(c.from_lane).road_id for c in conns):
        r = net.road(road)
        line = r.lanes[0].centreline
        hx, hy = np.abs(line[-1, :2] - line[-2, :2]) / np.linalg.norm(line[-1, :2] - line[-2, :2])
        width = float(hx * (x1 - x0) + hy * (y1 - y0))  # box extent along the approach
        v = r.speed_limit_mps
        amber = PERCEPTION_REACTION_S + v / (2.0 * ITE_DECEL_MPS2)
        all_red = (width + CLEARANCE_VEHICLE_LENGTH_M) / v
        ids = tuple(c.id for c in conns if net.lane(c.from_lane).road_id == road)
        phases.append(Phase(road, ids, amber, all_red))
    return phases


def movement_flows(net: Network, routes, lg, demand, j: Junction) -> dict[str, float]:
    """veh/h per connector of junction j from the OD demand (equal split over lanes)."""
    conns = [c for c in net.connectors if c.junction_id == j.id]
    out = {c.id: 0.0 for c in conns}
    for f in demand:
        if f.veh_per_h <= 0:
            continue
        roads = routes.roads[routes.add(net, lg, f.origin, f.destination)]
        for a, b in zip(roads[:-1], roads[1:], strict=True):
            cands = [
                c for c in conns
                if net.lane(c.from_lane).road_id == a and net.lane(c.to_lane).road_id == b
            ]  # fmt: skip
            for c in cands:
                out[c.id] += f.veh_per_h / len(cands)
    return out


def phase_startup_lost(phases: list[Phase], flows: dict[str, float],
                       startup_lost: dict[str, float]) -> list[float]:  # fmt: skip
    """Measured l1 per phase: flow-weighted mean over its movements (plain mean if no flow)."""
    out = []
    for ph in phases:
        q = np.array([flows[c] for c in ph.connector_ids])
        l1 = np.array([startup_lost[c] for c in ph.connector_ids])
        out.append(float(np.average(l1, weights=q) if q.sum() > 0 else l1.mean()))
    return out


def webster_plan(phases: list[Phase], flows: dict[str, float], sat: dict[str, float],
                 startup_lost: dict[str, float], net: Network) -> WebsterPlan:  # fmt: skip
    ys = []
    for ph in phases:
        lane_y: dict[str, float] = {}
        for cid in ph.connector_ids:
            lane = next(c.from_lane for c in net.connectors if c.id == cid)
            lane_y[lane] = lane_y.get(lane, 0.0) + flows[cid] / sat[cid]
        ys.append(max(lane_y.values()))
    Y = float(sum(ys))
    l1 = phase_startup_lost(phases, flows, startup_lost)
    lost = sum(a + ph.intergreen_s - GREEN_EXTENSION_S for a, ph in zip(l1, phases, strict=True))
    c_min = sum(G_MIN_S + ph.intergreen_s for ph in phases)
    c0 = (1.5 * lost + 5.0) / (1.0 - Y) if Y < 1.0 else float("inf")
    cycle = min(max(c0, c_min), C_MAX_S)
    offset = [a - GREEN_EXTENSION_S for a in l1]  # displayed green = effective + (l1 - e)
    greens = _split_greens(cycle - sum(ph.intergreen_s for ph in phases), ys, offset)
    return WebsterPlan(cycle, tuple(greens), tuple(ys), Y, lost, c0, Y >= 1.0, tuple(l1))


def _split_greens(total_green: float, ys: list[float], offset: list[float]) -> list[float]:
    """Displayed green G_k = g_k + offset_k with effective green g_k ∝ y_k, G_k ≥ G_MIN.

    ``total_green`` = C − Σ intergreen is the displayed green; Σ g_k = C − L = total −
    Σ offset. Phases whose share falls below G_MIN get G_MIN and the rest is re-split over
    the others ∝ y, so the cycle length is preserved (C ≥ C_min guarantees feasibility).
    """
    n = len(ys)
    fixed: dict[int, float] = {}
    while True:
        free = [k for k in range(n) if k not in fixed]
        rest = total_green - sum(fixed.values()) - sum(offset[k] for k in free)
        y_free = sum(ys[k] for k in free)
        share = {k: (ys[k] / y_free if y_free > 0 else 1.0 / len(free)) for k in free}
        low = [k for k in free if offset[k] + rest * share[k] < G_MIN_S]
        if not low:
            return [fixed.get(k, offset[k] + rest * share.get(k, 0.0)) for k in range(n)]
        for k in low:
            fixed[k] = G_MIN_S
