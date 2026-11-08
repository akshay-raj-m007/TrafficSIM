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

Measuring takes about 8 s, so for the demo network and the default vehicle mix the result
is also kept in a committed table (``trafficsim/data/calibration_demo.json``, written by
``backend/tools/gen_calibration.py``) with a digest of every input that determines it
(the same digest as the free-flow table plus the mix). A stale table is ignored (the
values are measured instead), a test fails when it is stale, and another test re-measures
to prove the table equals what the engine produces.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path

import numpy as np

from trafficsim.engine import tablecache
from trafficsim.engine.params.control import (
    CALIBRATION_SEED,
    SAT_QUEUE_VEHICLES,
    SAT_SKIP_VEHICLES,
    STOP_LINE_STANDOFF_M,
)
from trafficsim.engine.scenario import DEFAULT_MIX
from trafficsim.engine.vehicle import CLASS_INDEX, LEN, S0
from trafficsim.network.types import Network

TABLE_PATH = Path(__file__).resolve().parents[1] / "data" / "calibration_demo.json"
TABLE_PATH_J2_1 = TABLE_PATH.with_name("calibration_demo_j2_1.json")  # one-lane J2 network

DISCHARGE_TIMEOUT_S = 300.0  # generous upper bound for one queue to discharge [s]
_cache: dict[tuple, dict[str, tuple[float, float]]] = {}  # conn -> (sat flow, start-up loss)
_lock = threading.Lock()  # one measurement at a time; a second caller finds the result


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


def table_digest(net: Network, mix) -> str:
    """Digest of every input of the calibration (see engine/freeflow.input_digest)."""
    from trafficsim.engine.freeflow import input_digest
    from trafficsim.engine.lanegraph import compile_network

    return hashlib.sha256(
        (input_digest(net, compile_network(net)) + repr(tuple(mix))).encode()
    ).hexdigest()


def _from_doc(doc: dict | None, digest: str, junction_id: str):
    if doc and doc["digest"] == digest and junction_id in doc["junctions"]:
        return {
            c: (v["sat_flow_veh_h"], v["startup_lost_s"])
            for c, v in doc["junctions"][junction_id].items()
        }
    return None


def _from_table(net: Network, mix, junction_id: str):
    """Committed table (default mix), else the on-disk cache (any mix); None if neither."""
    digest = table_digest(net, mix)
    if tuple(mix) == tuple(DEFAULT_MIX):
        for path in (TABLE_PATH, TABLE_PATH_J2_1):
            if path.exists():
                got = _from_doc(json.loads(path.read_text(encoding="utf-8")), digest, junction_id)
                if got:
                    return got
    return _from_doc(tablecache.load("calibration", digest), digest, junction_id)


def _store(net: Network, mix, junction_id: str, got: dict[str, tuple[float, float]]) -> None:
    digest = table_digest(net, mix)
    doc = tablecache.load("calibration", digest) or {"digest": digest, "junctions": {}}
    doc["junctions"][junction_id] = {
        c: {"sat_flow_veh_h": v[0], "startup_lost_s": v[1]} for c, v in got.items()
    }
    tablecache.store("calibration", digest, doc)


# Called as (done, total) after each connector of a measurement (the server shows progress while
# a layout is prepared for the first time). A ContextVar, so each build thread has its own.
progress_hook: ContextVar[Callable[[int, int], None] | None] = ContextVar("progress", default=None)


def _measure(net: Network, mix, junction_id: str) -> dict[str, tuple[float, float]]:
    conns = [c.id for c in net.connectors if c.junction_id == junction_id]
    out = {}
    for done, cid in enumerate(conns, 1):
        out[cid] = _discharge(net, mix, junction_id, cid)
        if (hook := progress_hook.get()) is not None:
            hook(done, len(conns))
    return out


def measurement_steps(net: Network, mix) -> int:
    """Connectors still to be measured for this network and mix (0: all tables are known)."""
    return sum(
        sum(1 for c in net.connectors if c.junction_id == j.id)
        for j in net.junctions
        if j.control == "signalised" and _from_table(net, mix, j.id) is None
    )


def _calibrate(net: Network, mix, junction_id: str) -> dict[str, tuple[float, float]]:
    key = (id(net), tuple(mix), junction_id)
    if key not in _cache:
        with _lock:
            if key not in _cache:
                got = _from_table(net, mix, junction_id)
                if got is None:
                    got = _measure(net, mix, junction_id)  # about 8 s, once per mix and machine
                    _store(net, mix, junction_id, got)
                _cache[key] = got
    return _cache[key]


def write_table(net: Network, path: Path = TABLE_PATH) -> None:
    """Measure every signalised junction for the default mix and write the table."""
    junctions = {
        j.id: {
            c: {"sat_flow_veh_h": round(v[0], 6), "startup_lost_s": round(v[1], 6)}
            for c, v in _measure(net, DEFAULT_MIX, j.id).items()
        }
        for j in net.junctions
        if j.control == "signalised"
    }
    doc = {"digest": table_digest(net, DEFAULT_MIX), "junctions": junctions}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


def saturation_flows(net: Network, mix, junction_id: str) -> dict[str, float]:
    """Measured saturation flow [veh/h] per connector id of one junction (cached)."""
    return {cid: v[0] for cid, v in _calibrate(net, mix, junction_id).items()}


def startup_lost_times(net: Network, mix, junction_id: str) -> dict[str, float]:
    """Measured start-up lost time [s] per connector id of one junction (cached)."""
    return {cid: v[1] for cid, v in _calibrate(net, mix, junction_id).items()}
