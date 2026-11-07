"""Headless run -> per-run metrics for A/B comparisons. Every metric is measured.

Window and cohort (written down once, README "A/B comparison"):
  * the run covers [0, duration); statistics use the window [warm-up, duration);
  * trip-level metrics (delay, travel time, flyover share) use the COHORT: vehicles
    generated at or after the warm-up end (nothing from the empty-network start enters)
    that had at least their own free-flow trip time left before the end. The second
    condition depends on the generation time and the route only, never on the outcome, so
    it treats A and B alike; it keeps a vehicle that was merely generated a minute before
    the end (and so could not have finished) from counting as "zero delay". Excluded ones
    are counted (``counts.too_young``) and still appear in throughput and unserved demand;
  * throughput counts completed trips that EXIT inside the window (a flow);
  * queues use the 1 s samples taken inside the window.

Delay is measured against the fastest free-flow route on the fully OPEN network for the
vehicle's origin and destination and class, whatever route it takes, so the extra time a
closure causes is delay (engine/freeflow.py ``DelayReference``).

Unfinished trips are not dropped. ``mean_delay_s`` (the primary metric) covers every
cohort vehicle: a completed trip contributes (t_exit - t_gen) - free_flow, an unfinished one
(in the network or waiting at an entry) the lower bound max(0, (t_end - t_gen) - free_flow):
its final delay can only be larger. Delay includes waiting at the entry.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafficsim.engine.constants import STEPS_PER_SECOND, ticks_for
from trafficsim.engine.freeflow import DelayReference, all_keys, reference_for
from trafficsim.engine.loop import Simulation
from trafficsim.engine.presets import DEMO_KPI_LAYOUT
from trafficsim.engine.queues import QueueMeter
from trafficsim.engine.scenario import Scenario
from trafficsim.network.routing import fastest_route, grade_separated_roads
from trafficsim.network.types import Network

METRICS_VERSION = 2  # bump when a definition changes: cached / shipped results go stale
SAMPLE_EVERY_STEPS = STEPS_PER_SECOND  # queue samples and flyover tracking every 1 s
J1_APPROACHES = ("J1_W", "J1_E", "J1_N", "J1_S")
J2_APPROACHES = ("J2_W", "J2_E", "J2_N")

# metric id -> (label, unit); order is the order of the results table
METRICS: dict[str, tuple[str, str]] = {
    "mean_delay_s": ("Mean delay, all trips (unfinished: lower bound)", "s"),
    "mean_delay_completed_s": ("Mean delay, completed trips only", "s"),
    "tt_p50_s": ("Travel time p50 (completed)", "s"),
    "tt_p90_s": ("Travel time p90 (completed)", "s"),
    "throughput_veh_h": ("Throughput (completed trips in window)", "veh/h"),
    "unserved_veh": ("Unserved demand (waiting at entries at the end)", "veh"),
    "unfinished_veh": ("Unfinished trips (cohort, at the end)", "veh"),
    "j1_queue_max_m": ("J1 longest approach queue, maximum", "m"),
    "j1_queue_mean_m": ("J1 longest approach queue, time average", "m"),
    "j2_queue_max_m": ("J2 longest approach queue, maximum", "m"),
    "j2_queue_mean_m": ("J2 longest approach queue, time average", "m"),
    "flyover_share": ("Flyover share of eligible trips", "ratio"),
}


@dataclass(frozen=True, slots=True)
class Trip:
    t_gen: float
    t_exit: float | None  # None: unfinished at the end
    free_flow_s: float
    od: tuple[str, str]
    vid: int


def _mean(a) -> float | None:
    return float(np.mean(a)) if len(a) else None


def summarise(trips: list[Trip], warmup_s: float, end_s: float, used_flyover: set[int],
              eligible: set[tuple[str, str]], unserved: int) -> dict:  # fmt: skip
    """Trip-level metrics of one run from plain records (pure; see the module docstring)."""
    cohort = [t for t in trips if t.t_gen >= warmup_s and end_s - t.t_gen >= t.free_flow_s]
    young = sum(t.t_gen >= warmup_s for t in trips) - len(cohort)
    done = [t for t in cohort if t.t_exit is not None]
    open_ = [t for t in cohort if t.t_exit is None]
    d_done = [(t.t_exit - t.t_gen) - t.free_flow_s for t in done]
    d_open = [max(0.0, (end_s - t.t_gen) - t.free_flow_s) for t in open_]
    tt = [t.t_exit - t.t_gen for t in done]
    exits_in_window = [t for t in trips if t.t_exit is not None and t.t_exit >= warmup_s]
    elig = [t for t in done if t.od in eligible]
    window_h = (end_s - warmup_s) / 3600.0
    return {
        "mean_delay_s": _mean(d_done + d_open),
        "mean_delay_completed_s": _mean(d_done),
        "tt_p50_s": float(np.percentile(tt, 50)) if tt else None,
        "tt_p90_s": float(np.percentile(tt, 90)) if tt else None,
        "throughput_veh_h": len(exits_in_window) / window_h,
        "unserved_veh": float(unserved),
        "unfinished_veh": float(len(open_)),
        "flyover_share": (sum(t.vid in used_flyover for t in elig) / len(elig)) if elig else None,
        "counts": {"cohort": len(cohort), "completed": len(done), "unfinished": len(open_),
                   "too_young": young, "exits_in_window": len(exits_in_window)},
    }  # fmt: skip


def flyover_pairs(net: Network) -> set[tuple[str, str]]:
    """OD pairs whose open-network fastest route uses the flyover (the 'eligible' trips)."""
    fly = grade_separated_roads(net)
    return {
        (o.id, d.id)
        for o in net.zones
        for d in net.zones
        if o.id != d.id and fly & set(fastest_route(net, o.id, d.id) or ())
    }


def run_metrics(net: Network, scenario: Scenario, warmup_s: float) -> dict:
    """Run ``scenario`` to its end and return the metrics of the window [warmup, duration)."""
    if not 0.0 <= warmup_s < scenario.duration_s:
        raise ValueError(f"warm-up {warmup_s} s must be in [0, duration {scenario.duration_s} s)")
    ticks_for(warmup_s)  # a multiple of DT
    sim = Simulation(net, scenario)
    lg, rt = sim.lg, sim.routes
    ref = reference_for(net, lg)
    ref.request(all_keys(net), background=False)  # a no-op when the committed table is current
    meter = QueueMeter(lg, DEMO_KPI_LAYOUT.approaches)
    ids = [s.id for s in DEMO_KPI_LAYOUT.approaches]
    j1 = [ids.index(a) for a in J1_APPROACHES]
    j2 = [ids.index(a) for a in J2_APPROACHES]
    fly = grade_separated_roads(net)
    fly_segs = np.array([k for k, r in enumerate(lg.road_of) if r in fly], dtype=np.int64)
    used: set[int] = set()
    q1: list[float] = []
    q2: list[float] = []
    warm_tick = ticks_for(warmup_s)
    while sim.tick < ticks_for(scenario.duration_s):
        sim.step_n(SAMPLE_EVERY_STEPS)
        used.update(sim.vehicles.vid[np.isin(sim.vehicles.seg, fly_segs)].tolist())
        if sim.tick > warm_tick:
            q = meter.measure(sim.vehicles)
            q1.append(max(q[i][1] for i in j1))
            q2.append(max(q[i][1] for i in j2))

    delay_ref = DelayReference(net, ref)

    def trip(t_gen: float, t_exit: float | None, route: int, cls: int, vid: int) -> Trip:
        pair = rt.pair[route]
        ff = delay_ref.free_flow(pair, cls)
        if ff is None:
            raise RuntimeError(f"no free-flow time for {pair} class {cls}")
        return Trip(t_gen, t_exit, ff, pair, vid)

    trips = [trip(e.t_gen, e.t_exit, e.route, e.cls, e.vid) for e in sim.log.exits]
    vs = sim.vehicles
    trips += [
        trip(float(vs.t_gen[i]), None, int(vs.route[i]), int(vs.cls[i]), int(vs.vid[i]))
        for i in range(vs.n)
    ]
    waiting = [q for z in sim.demand.zones for q in z.queue]
    trips += [trip(q.t_gen, None, q.route, q.cls, -1) for q in waiting]
    out = summarise(trips, warmup_s, sim.time_s, used, flyover_pairs(net), len(waiting))
    out.update(
        j1_queue_max_m=max(q1), j1_queue_mean_m=float(np.mean(q1)),
        j2_queue_max_m=max(q2), j2_queue_mean_m=float(np.mean(q2)),
    )  # fmt: skip
    out["counts"]["generated"] = sim.demand.generated
    out["counts"]["oldest_wait_s"] = max((sim.time_s - q.t_gen for q in waiting), default=0.0)
    return out
