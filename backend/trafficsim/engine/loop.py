"""The simulation loop: advances a fixed time step DT = 0.1 s.

Phase order inside ``step`` (fixed; later phases slot in without changing it):

    1. signals     update controller states            (part 4)
    2. demand      arrivals → entry queues → insertion
    3. leaders     occupancy, leaders, stop lines / lane ends, junction gates
    4. decisions   MOBIL lane changes (mandatory first), then leaders are refreshed
    5. dynamics    IDM + power/grade + anticipation, ballistic update
    6. transfer    move across segment ends, exits
    7. clock       tick += 1

The engine has no notion of wall-clock time: real-time pacing is the server's job.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.constants import DT, time_of
from trafficsim.engine.demand import Demand
from trafficsim.engine.dynamics import accelerations
from trafficsim.engine.idm import ballistic_update
from trafficsim.engine.lanegraph import compile_network
from trafficsim.engine.lc_sync import mandatory_offsets, sync_accel
from trafficsim.engine.leaders import build_occupancy, find_leaders, stop_gaps
from trafficsim.engine.mobil import lane_changes
from trafficsim.engine.params.driving import B_EMERGENCY_MPS2
from trafficsim.engine.rng import RngStreams
from trafficsim.engine.routes import RouteTable
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.transfer import TransferLog, advance_segments
from trafficsim.engine.vehicle import CLASS_INDEX, VehicleState
from trafficsim.network.types import Network


class Simulation:
    dt: float = DT

    def __init__(self, network: Network, scenario: Scenario) -> None:
        self.network = network
        self.scenario = scenario
        self.rng = RngStreams(scenario.seed)
        self.lg = compile_network(network)
        self.routes = RouteTable()
        self.demand = Demand(network, self.lg, self.routes, scenario, self.rng)
        self.vehicles = VehicleState.empty()
        self.log = TransferLog()
        self.emergency_brakings = 0
        self.lane_changes = 0
        self.mandatory_lane_changes = 0
        self.tick: int = 0
        self._total_ticks = scenario.total_ticks

    # ----------------------------------------------------------------- clock
    @property
    def time_s(self) -> float:
        """Simulated time [s], exact: derived from the integer tick, never accumulated."""
        return time_of(self.tick)

    @property
    def done(self) -> bool:
        return self.tick >= self._total_ticks

    # ------------------------------------------------------------- counters
    @property
    def exited(self) -> int:
        return len(self.log.exits)

    @property
    def active(self) -> int:
        return self.vehicles.n

    def place_vehicle(
        self, origin: str, dest: str, cls_name: str, lane_index: int, s: float, v: float
    ) -> int:
        """Put a scripted vehicle on the origin's entry road (controlled experiments).

        Bypasses the arrival process but not the bookkeeping: it is counted as generated
        and inserted, so conservation still holds. Returns its vehicle id.
        """
        route = self.routes.add(self.network, self.lg, origin, dest)
        seg = self.lg.road_segs[self.routes.roads[route][0]][lane_index]
        return self.demand.place(
            self.vehicles, route, CLASS_INDEX[cls_name], seg, s, v, self.time_s
        )

    def row_of(self, vid: int) -> int | None:
        rows = np.flatnonzero(self.vehicles.vid == vid)
        return int(rows[0]) if rows.size else None

    # ------------------------------------------------------------- stepping
    def step(self) -> bool:
        """Advance one DT. Returns False (and does nothing) once the scenario has ended."""
        if self.done:
            return False
        t = self.time_s
        vs, lg = self.vehicles, self.lg
        self.demand.generate(t)
        self.demand.insert(vs, t)
        occ = build_occupancy(vs, lg)
        gap, v_lead = find_leaders(vs, lg, self.routes, occ)
        changes, mandatory = lane_changes(
            vs, lg, self.routes, occ, gap, v_lead, self.tick, self.log, t
        )
        if changes:
            self.lane_changes += changes
            self.mandatory_lane_changes += mandatory
            occ = build_occupancy(vs, lg)
            gap, v_lead = find_leaders(vs, lg, self.routes, occ)
        acc = accelerations(vs, lg, gap, v_lead, stop_gaps(vs, lg))
        rows, a_sync = sync_accel(vs, lg, occ, mandatory_offsets(vs))
        acc[rows] = np.minimum(acc[rows], a_sync)
        v_before = vs.v
        vs.s, vs.v = ballistic_update(vs.s, vs.v, acc)
        # Diagnostic on the deceleration actually realised (a standing vehicle's IDM
        # command can be very negative without any physical braking happening).
        vs.acc = (vs.v - v_before) / DT
        self.emergency_brakings += int(np.count_nonzero(vs.acc < -B_EMERGENCY_MPS2))
        vs.lc_timer = vs.lc_timer + DT
        self.tick += 1
        advance_segments(vs, lg, self.routes, self.time_s, self.log)
        return True

    def step_n(self, n: int) -> int:
        """Advance up to ``n`` steps; returns how many were actually taken."""
        if n < 0:
            raise ValueError("n must be non-negative")
        taken = 0
        while taken < n and self.step():
            taken += 1
        return taken

    def run_until(self, t_s: float) -> int:
        """Advance until simulated time reaches ``t_s`` (or the scenario ends)."""
        target = round(t_s / DT)
        return self.step_n(max(0, target - self.tick))
