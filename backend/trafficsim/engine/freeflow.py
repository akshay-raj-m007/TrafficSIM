"""Free-flow travel time per (route, vehicle class), measured by the engine itself.

One vehicle alone on an otherwise empty network, signals off, inserted by the regular
insertion rule (``Demand.insert_now``): grade (power limit), turn-curvature limits,
lane-width factors, the lane choice at the diverge and mandatory lane changes are all in
the number, because it is the same model. The delay of a real vehicle is then
(t_exit − t_ins) − free_flow(route, class): no formula, no fudge.

Reference runs for one network are done sequentially in a single private simulation (the
next vehicle enters only after the previous one has left). They take about a minute, so
the demo network's values live in a committed table (``trafficsim/data/``), regenerated
by ``backend/tools/gen_freeflow.py``. The table carries a digest of every input that
determines it (lane graph, vehicle classes, model constants); if the digest no longer
matches, the table is ignored and the missing values are measured in a background thread
(``get`` returns None until then). A test fails when the committed table is stale, and
another re-measures a sample to prove the table equals what the engine produces.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import numpy as np

from trafficsim.network.types import Network

TABLE_PATH = Path(__file__).resolve().parents[1] / "data" / "freeflow_demo.json"
# second committed table: the old one-lane J2 minor approach (a digest picks the right one)
TABLE_PATH_J2_1 = TABLE_PATH.with_name("freeflow_demo_j2_1.json")

_MAX_RUN_S = 900.0  # a free vehicle must finish a route in well under this [s]
_registry: dict[int, FreeFlowReference] = {}
_registry_lock = threading.Lock()


def input_digest(net: Network, lg) -> str:
    """Digest of everything that determines the free-flow times."""
    from trafficsim.engine import vehicle
    from trafficsim.engine.params import control, driving

    h = hashlib.sha256()
    arrays = (lg.length, lg.vlimit, lg.width, lg.v0_eff, vehicle.LEN, vehicle.V0, vehicle.T)
    for a in (*arrays, vehicle.A, vehicle.B, vehicle.S0, vehicle.P2M):
        h.update(np.round(np.asarray(a, dtype=float), 6).tobytes())
    for seg in sorted(lg.profiles):
        for a in lg.profiles[seg]:
            h.update(np.round(a, 6).tobytes())
    for mod in (driving, control):
        for k in sorted(vars(mod)):
            v = getattr(mod, k)
            if k.isupper() and isinstance(v, int | float):
                h.update(f"{k}={v!r}".encode())
    h.update(json.dumps(sorted(all_route_roads(net))).encode())
    return h.hexdigest()


def all_route_roads(net: Network) -> list[tuple[str, ...]]:
    """The fastest route (road sequence) of every ordered origin-destination zone pair."""
    from trafficsim.network.routing import fastest_route

    out: list[tuple[str, ...]] = []
    for o in net.zones:  # the fully open network: the reference of every delay
        for d in net.zones:
            route = tuple(fastest_route(net, o.id, d.id)) if o.id != d.id else None
            if route and route not in out:
                out.append(route)
    return out


def all_keys(net: Network) -> list[tuple[tuple[str, ...], int]]:
    from trafficsim.engine.vehicle import VEHICLE_CLASSES

    return [(r, c) for r in all_route_roads(net) for c in range(len(VEHICLE_CLASSES))]


class DelayReference:
    """Free-flow time of a vehicle's trip: the fastest route on the fully open network for its
    (origin, destination) and class, whatever route it actually takes (so a detour forced by a
    closure is delay). None until the engine has measured it."""

    def __init__(self, net: Network, ref: FreeFlowReference) -> None:
        self.net, self.ref = net, ref
        self._roads: dict[tuple[str, str], tuple[str, ...]] = {}

    def roads(self, pair: tuple[str, str]) -> tuple[str, ...]:
        if pair not in self._roads:
            from trafficsim.network.routing import fastest_route

            route = fastest_route(self.net, *pair)
            if route is None:
                raise ValueError(f"no route from {pair[0]} to {pair[1]}")
            self._roads[pair] = tuple(route)
        return self._roads[pair]

    def free_flow(self, pair: tuple[str, str], cls: int) -> float | None:
        return self.ref.get(self.roads(pair), cls)


def reference_for(net: Network, lg=None) -> FreeFlowReference:
    with _registry_lock:
        if id(net) not in _registry:
            _registry[id(net)] = FreeFlowReference(net, lg)
        return _registry[id(net)]


class FreeFlowReference:
    def __init__(self, net: Network, lg=None) -> None:
        self.net = net
        self._values: dict[tuple[tuple[str, ...], int], float] = {}
        self.table_used = False
        if lg is not None:
            digest = input_digest(net, lg)
            for path in (TABLE_PATH, TABLE_PATH_J2_1):
                if not path.exists():
                    continue
                table = json.loads(path.read_text(encoding="utf-8"))
                if table["digest"] == digest:
                    for e in table["values"]:
                        self._values[(tuple(e["roads"]), e["cls"])] = e["t_s"]
                    self.table_used = True
                    break
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.seconds_to_compute = 0.0  # wall time of the last batch (diagnostic)

    def write_table(self, lg, path: Path = TABLE_PATH) -> None:
        keys = all_keys(self.net)
        self.request(keys, background=False)
        values = [
            {"roads": list(r), "cls": c, "t_s": round(self._values[(r, c)], 6)} for r, c in keys
        ]
        doc = {"digest": input_digest(self.net, lg), "values": values}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")

    def get(self, roads: tuple[str, ...], cls: int) -> float | None:
        return self._values.get((roads, cls))

    def ready(self, keys) -> bool:
        return all(k in self._values for k in keys)

    def request(self, keys, background: bool = True) -> None:
        """Make sure every (roads, class) in ``keys`` gets measured."""
        todo = [k for k in dict.fromkeys(keys) if k not in self._values]
        if not todo:
            return
        if not background:
            self._measure(todo)
            return
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._measure, args=(todo,), daemon=True, name="freeflow"
                )
                self._thread.start()
            else:  # a batch is running: queue another after it
                prev = self._thread
                self._thread = threading.Thread(
                    target=lambda: (prev.join(), self._measure(todo)), daemon=True
                )
                self._thread.start()

    def _measure(self, todo) -> None:
        import time

        from trafficsim.engine.loop import Simulation  # local: loop imports kpi -> this module
        from trafficsim.engine.scenario import Scenario

        t0 = time.perf_counter()
        sim = Simulation(
            self.net,
            Scenario(duration_s=_MAX_RUN_S * (len(todo) + 1), signal_control="uncontrolled"),
        )
        for roads, cls in todo:
            if (roads, cls) in self._values:
                continue
            route = sim.routes.add_explicit(sim.lg, roads, ("freeflow", "|".join(roads) + str(cls)))
            n_exit = len(sim.log.exits)
            if sim.demand.insert_now(sim.vehicles, route, cls, sim.time_s) is None:
                raise RuntimeError(f"free-flow vehicle could not be inserted on {roads[0]}")
            limit = sim.tick + int(_MAX_RUN_S * 10)
            while len(sim.log.exits) == n_exit and sim.tick < limit:
                sim.step()
            if len(sim.log.exits) == n_exit:
                raise RuntimeError(f"free-flow vehicle did not finish route {roads}")
            e = sim.log.exits[-1]
            self._values[(roads, cls)] = e.t_exit - e.t_ins
        self.seconds_to_compute = time.perf_counter() - t0
