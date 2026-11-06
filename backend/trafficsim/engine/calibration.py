"""Saturation flow measured in the simulation itself (no assumed 1800/1900 veh/h).

For each signalised junction connector (turning movement) a standing queue of
SAT_QUEUE_VEHICLES vehicles, drawn from the scenario's vehicle mix, is placed on the
movement's approach lane with no signal and no other traffic, then released. The
saturation headway is the mean line-crossing headway of the vehicles after the
SAT_SKIP_VEHICLES-th (HCM 6th ed., Ch. 31 field procedure); saturation flow =
3600 / headway [veh/h]. The start-up lost time is measured in the same run (HCM
definition): time at which the SAT_SKIP_VEHICLES-th vehicle crosses the line, counted
from the release, minus SAT_SKIP_VEHICLES saturation headways. Results are cached per
(network, mix).
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.params.control import (
    CALIBRATION_SEED,
    SAT_QUEUE_VEHICLES,
    SAT_SKIP_VEHICLES,
    STOP_LINE_STANDOFF_M,
)
from trafficsim.engine.vehicle import CLASS_INDEX, LEN, S0
from trafficsim.network.types import Network

DISCHARGE_TIMEOUT_S = 300.0  # generous upper bound for one queue to discharge [s]
_cache: dict[tuple, dict[str, tuple[float, float]]] = {}  # conn -> (sat flow, start-up loss)


def _route_through(sim, conn_seg: int) -> tuple[int, int]:
    """A two-road route (approach road, exit road) whose path takes ``conn_seg``."""
    lg = sim.lg
    a, b = int(lg.conn_from[conn_seg]), int(lg.conn_to[conn_seg])
    roads = (lg.road_of[a], lg.road_of[b])
    return sim.routes.add_explicit(lg, roads, ("calibration", lg.ids[conn_seg])), 0


def _discharge(net: Network, mix, junction_id: str, conn_id: str) -> tuple[float, float]:
    from trafficsim.engine.loop import Simulation  # local import: loop builds controllers
    from trafficsim.engine.scenario import Scenario

    sim = Simulation(net, Scenario(seed=CALIBRATION_SEED, duration_s=DISCHARGE_TIMEOUT_S,
                                   vehicle_mix=mix, signal_control="uncontrolled"))  # fmt: skip
    lg = sim.lg
    c = lg.seg_of[conn_id]
    route, rpos = _route_through(sim, c)
    sim.allow_lane_changes = False  # measure one lane's discharge only
    a = int(lg.conn_from[c])
    names = [n for n, _ in mix]
    p = np.array([w for _, w in mix])
    classes = sim.rng.vehicle_class.choice(len(names), size=SAT_QUEUE_VEHICLES, p=p)
    front = float(lg.length[a]) - STOP_LINE_STANDOFF_M
    vids = []
    for k in classes:
        cls = CLASS_INDEX[names[int(k)]]
        vids.append(sim.demand.place(sim.vehicles, route, cls, a, front, 0.0, 0.0, rpos))
        front -= float(LEN[cls] + S0[cls])
        if front <= float(LEN.max()):
            raise ValueError(f"approach lane of {conn_id} too short for the calibration queue")
    times: dict[int, float] = {}
    seen = 0
    while len(times) < len(vids) and not sim.done:
        sim.step()
        for e in sim.log.junction_entries[seen:]:
            if e.conn == c:
                times[e.vid] = e.t
        seen = len(sim.log.junction_entries)
    t = np.array([times[v] for v in vids if v in times])
    if t.size < SAT_QUEUE_VEHICLES:
        raise RuntimeError(f"calibration queue on {conn_id} did not discharge")
    h_sat = float(np.diff(t[SAT_SKIP_VEHICLES:]).mean())
    startup_lost = float(t[SAT_SKIP_VEHICLES - 1]) - SAT_SKIP_VEHICLES * h_sat
    return 3600.0 / h_sat, startup_lost


def _calibrate(net: Network, mix, junction_id: str) -> dict[str, tuple[float, float]]:
    key = (id(net), tuple(mix), junction_id)
    if key not in _cache:
        conns = [c.id for c in net.connectors if c.junction_id == junction_id]
        _cache[key] = {cid: _discharge(net, mix, junction_id, cid) for cid in conns}
    return _cache[key]


def saturation_flows(net: Network, mix, junction_id: str) -> dict[str, float]:
    """Measured saturation flow [veh/h] per connector id of one junction (cached)."""
    return {cid: v[0] for cid, v in _calibrate(net, mix, junction_id).items()}


def startup_lost_times(net: Network, mix, junction_id: str) -> dict[str, float]:
    """Measured start-up lost time [s] per connector id of one junction (cached)."""
    return {cid: v[1] for cid, v in _calibrate(net, mix, junction_id).items()}
