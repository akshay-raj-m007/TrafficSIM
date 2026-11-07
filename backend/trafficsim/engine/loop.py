"""The simulation loop: advances a fixed time step DT = 0.1 s.

Phase order inside ``step`` (fixed; later phases slot in without changing it):

    1. signals     advance J1 controller (fixed-time Webster or max-pressure)
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

from trafficsim.engine.changes import apply_due, schedule_change
from trafficsim.engine.constants import DT, STEPS_PER_SECOND, time_of
from trafficsim.engine.demand import Demand
from trafficsim.engine.dynamics import accelerations
from trafficsim.engine.gates import JunctionGates
from trafficsim.engine.idm import ballistic_update
from trafficsim.engine.kpi import KpiHub, KpiLayout
from trafficsim.engine.lanegraph import compile_network
from trafficsim.engine.lc_sync import mandatory_offsets, sync_accel
from trafficsim.engine.leaders import build_occupancy, find_leaders, stop_gaps
from trafficsim.engine.mobil import lane_changes
from trafficsim.engine.params.control import (
    INCIDENT_LENGTH_M,
    QUEUE_SAMPLE_PERIOD_S,
    V_QUEUED_MPS,
)
from trafficsim.engine.params.driving import B_EMERGENCY_MPS2
from trafficsim.engine.rng import RngStreams
from trafficsim.engine.routes import RouteTable
from trafficsim.engine.scenario import Change, Scenario
from trafficsim.engine.signals import make_controllers, make_design
from trafficsim.engine.transfer import TransferLog, advance_segments
from trafficsim.engine.vehicle import CLASS_INDEX, VehicleState
from trafficsim.network.routing import grade_separated_roads
from trafficsim.network.types import Network

SAMPLE_EVERY_STEPS = round(QUEUE_SAMPLE_PERIOD_S * STEPS_PER_SECOND)


class Simulation:
    dt: float = DT

    def __init__(
        self, network: Network, scenario: Scenario, kpi_layout: KpiLayout | None = None
    ) -> None:
        self.network = network
        self.scenario = scenario
        self.rng = RngStreams(scenario.seed)
        self.lg = compile_network(network)
        self.routes = RouteTable()
        self.flyover_open = scenario.flyover_open
        if not self.flyover_open:
            self.routes.closed = grade_separated_roads(network)
        self.flyover_pending = self.flyover_open  # state after the queued changes
        self.current_demand = scenario.demand
        self.current_mix = scenario.vehicle_mix
        self.policy = scenario.signal_control
        self.change_log: list[tuple[int, Change]] = []
        self._pending: list[tuple[int, Change]] = []
        self.rerouted = 0  # vehicles re-routed by a flyover change
        self.grandfathered_vids: set[int] = set()  # too close to the diverge to re-route (closure)
        self.demand = Demand(network, self.lg, self.routes, scenario, self.rng)
        self.vehicles = VehicleState.empty()
        self.gates = JunctionGates(network, self.lg)
        self.design = make_design(network, self.lg, self.routes, scenario)  # until the next reset
        self.signals = make_controllers(self.design, scenario.signal_control, self.lg)
        if self.signals:
            self.gates.signal = lambda c: all(ctrl.allows(c) for ctrl in self.signals)
        self._incidents = [(self.lg.seg_of[x.lane_id], x.s_m, x) for x in scenario.incidents]
        self.log = TransferLog()
        self.emergency_brakings = 0
        self.lane_changes = 0
        self.allow_lane_changes = True  # experiments (calibration) may switch this off
        self.box_stopped_vehicle_s = 0.0
        self.mandatory_lane_changes = 0
        self.kpis = KpiHub(self, kpi_layout)
        self.tick: int = 0
        self._total_ticks = scenario.total_ticks
        for tick, change in scenario.changes:
            self.schedule(change, tick)

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

    def _incident_obstacles(self, t: float):
        act = [(seg, s) for seg, s, x in self._incidents if x.active(t)]
        if not act:
            return None
        segs = np.array([a for a, _ in act], dtype=np.int64)
        return segs, np.array([b for _, b in act]), np.full(len(act), INCIDENT_LENGTH_M)

    def kpi_snapshot(self) -> dict:
        """Measured KPIs as a plain dict (see engine/kpi.py for every definition)."""
        return self.kpis.snapshot()

    def row_of(self, vid: int) -> int | None:
        rows = np.flatnonzero(self.vehicles.vid == vid)
        return int(rows[0]) if rows.size else None

    # ---------------------------------------------------------- live changes
    def schedule(self, change: Change, tick: int | None = None) -> int:
        """Queue a change for the start of ``tick`` (default: the next step); see changes.py."""
        return schedule_change(self, change, tick)

    @property
    def all_changes(self) -> list[tuple[int, Change]]:
        """Applied changes followed by the queued ones (what an export must contain)."""
        return self.change_log + self._pending

    # ------------------------------------------------------------- stepping
    def step(self) -> bool:
        """Advance one DT. Returns False (and does nothing) once the scenario has ended."""
        if self.done:
            return False
        if self._pending:
            apply_due(self)
        t = self.time_s
        vs, lg = self.vehicles, self.lg
        for ctrl in self.signals:
            ctrl.update(self.tick, vs, lg)
        self.demand.generate(t)
        self.demand.insert(vs, t)
        if vs.n == 0:  # nothing on the network: only the clock advances
            self.tick += 1
            return True
        static = self._incident_obstacles(t)
        occ = build_occupancy(vs, lg, static)
        self.gates.update(vs, occ)
        gap, v_lead = find_leaders(vs, lg, self.routes, occ, self.gates)
        changes, mandatory = (
            (0, 0)
            if not self.allow_lane_changes
            else lane_changes(vs, lg, self.routes, occ, gap, v_lead, self.tick, self.log, t)
        )
        if changes:
            self.lane_changes += changes
            self.mandatory_lane_changes += mandatory
            occ = build_occupancy(vs, lg, static)
            self.gates.update(vs, occ)
            gap, v_lead = find_leaders(vs, lg, self.routes, occ, self.gates)
        acc = accelerations(vs, lg, gap, v_lead, stop_gaps(vs, lg, self.gates))
        rows, a_sync = sync_accel(vs, lg, occ, mandatory_offsets(vs))
        acc[rows] = np.minimum(acc[rows], a_sync)
        v_before, s_before = vs.v, vs.s
        vs.s, vs.v = ballistic_update(vs.s, vs.v, acc)
        # Diagnostic on the deceleration actually realised (a standing vehicle's IDM
        # command can be very negative without any physical braking happening).
        vs.acc = (vs.v - v_before) / DT
        self.emergency_brakings += int(np.count_nonzero(vs.acc < -B_EMERGENCY_MPS2))
        vs.lc_timer = vs.lc_timer + DT
        self.tick += 1
        self.kpis.observe(vs, s_before, self.time_s)  # detector lines: before transfers
        advance_segments(
            vs, lg, self.routes, self.time_s, self.log, self.gates.room_seen,
            self.gates.may_enter, self.gates.commit_room,
        )  # fmt: skip
        # Physical outcome of spillback: vehicles held up inside a junction box (slower
        # than the queued-state speed AND not accelerating away from a standing start).
        in_box = lg.is_conn[vs.seg] & (vs.v < V_QUEUED_MPS) & (vs.acc <= 0.0)
        self.box_stopped_vehicle_s += float(np.count_nonzero(in_box)) * DT
        if self.tick % SAMPLE_EVERY_STEPS == 0:
            self.kpis.sample(self.time_s)
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
