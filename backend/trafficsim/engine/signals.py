"""Signal controllers for a signalised junction (approach-wise split phasing).

State machine per junction: GREEN(phase) → AMBER → ALL_RED → GREEN(next phase). Only
the green phase's connectors accept *new* entries; vehicles that committed before the
change keep their reservation (engine/gates.py), which is the amber dilemma-zone rule.

  FixedTimeWebster  cycles through the phases with Webster greens (engine/webster.py).
  MaxPressure       Varaiya (2013): pressure of a phase = Σ over its movements of
                    (queued upstream − queued downstream) × measured saturation flow;
                    after G_MIN the highest-pressure phase gets the green, a switch is
                    forced at G_MAX if another phase has queued vehicles. The textbook
                    rule, unchanged.
  MaxPressureThreshold  the same rule with (i) a longer minimum green and (ii) a switching
                    threshold: the best alternative must beat the current phase by the
                    capacity a switch forfeits. A switch costs a lost time
                    Ls = mean(amber + all-red) + mean measured start-up loss, during which
                    the junction could have discharged n = Ls · s_ref / 3600 vehicles
                    (s_ref = mean measured saturation flow of its movements). In pressure
                    units (vehicles × veh/h) that is threshold = n · s_ref. No free knob.
Durations are kept in whole ticks so the controller is exact and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.engine.params.control import (
    G_MAX_S,
    G_MIN_S,
    G_MIN_THRESHOLD_S,
    V_QUEUED_MPS,
)
from trafficsim.engine.webster import Phase, WebsterPlan


def _ticks(seconds: float) -> int:
    return max(1, round(seconds * STEPS_PER_SECOND))


class SignalController:
    def __init__(self, junction_id: str, phases: list[Phase], lg) -> None:
        self.junction_id = junction_id
        self.phases = phases
        self.phase_of = {lg.seg_of[c]: k for k, ph in enumerate(phases) for c in ph.connector_ids}
        self.amber = [_ticks(ph.amber_s) for ph in phases]
        self.all_red = [_ticks(ph.all_red_s) for ph in phases]
        self.phase, self.state, self.elapsed = 0, "green", 0
        self.next_phase = 0
        self.history: list[tuple[int, int, str]] = [(0, 0, "green")]  # (tick, phase, state)

    def allows(self, conn: int) -> bool:
        k = self.phase_of.get(conn)
        return k is None or (self.state == "green" and k == self.phase)

    def update(self, tick: int, vs, lg) -> None:
        self.elapsed += 1
        if self.state == "green":
            nxt = self._decide(vs, lg)
            if nxt is not None and nxt != self.phase:
                self.next_phase = nxt
                self._enter("amber", tick)
        elif self.state == "amber" and self.elapsed >= self.amber[self.phase]:
            self._enter("all_red", tick)
        elif self.state == "all_red" and self.elapsed >= self.all_red[self.phase]:
            self.phase = self.next_phase
            self._enter("green", tick)

    def _enter(self, state: str, tick: int) -> None:
        self.state, self.elapsed = state, 0
        self.history.append((tick, self.phase, state))

    def _decide(self, vs, lg) -> int | None:
        raise NotImplementedError


class FixedTimeWebster(SignalController):
    name = "fixed_webster"

    def __init__(self, junction_id: str, phases: list[Phase], lg, plan: WebsterPlan) -> None:
        super().__init__(junction_id, phases, lg)
        self.plan = plan
        self.green = [_ticks(g) for g in plan.greens_s]

    def _decide(self, vs, lg) -> int | None:
        if self.elapsed >= self.green[self.phase]:
            return (self.phase + 1) % len(self.phases)
        return None


class MaxPressure(SignalController):
    name = "max_pressure"

    def __init__(self, junction_id: str, phases: list[Phase], lg, sat: dict[str, float],
                 g_min_s: float = G_MIN_S, threshold: float = 0.0):  # fmt: skip
        super().__init__(junction_id, phases, lg)
        self.g_min, self.g_max = _ticks(g_min_s), _ticks(G_MAX_S)
        self.threshold = threshold  # pressure units: vehicles x veh/h
        self.movements = [
            [(lg.seg_of[c], int(lg.conn_to[lg.seg_of[c]]), sat[c]) for c in ph.connector_ids]
            for ph in phases
        ]
        self.last_pressure = np.zeros(len(phases))

    def pressures(self, vs, lg) -> tuple[np.ndarray, np.ndarray]:
        queued = vs.v < V_QUEUED_MPS
        nx = vs.nxt[queued]
        up = np.bincount(nx[nx >= 0], minlength=lg.n)
        down = np.bincount(vs.seg[queued], minlength=lg.n)
        p = np.array([sum((up[c] - down[to]) * s for c, to, s in mv) for mv in self.movements])
        waiting = np.array([sum(up[c] for c, _, _ in mv) for mv in self.movements])
        return p, waiting

    def _decide(self, vs, lg) -> int | None:
        if self.elapsed < self.g_min:
            return None
        p, waiting = self.pressures(vs, lg)
        self.last_pressure = p
        n = len(self.phases)
        others = [(self.phase + k) % n for k in range(1, n)]  # cyclic order breaks ties
        best = max(others, key=lambda k: p[k])
        if p[best] > p[self.phase] + self.threshold:
            return best
        if self.elapsed >= self.g_max and any(waiting[k] > 0 for k in others):
            return max((k for k in others if waiting[k] > 0), key=lambda k: p[k])
        return None


class MaxPressureThreshold(MaxPressure):
    name = "max_pressure_threshold"

    def __init__(self, junction_id: str, phases: list[Phase], lg, sat, startup_lost) -> None:
        s_ref = float(np.mean(list(sat.values())))  # veh/h
        lost = float(np.mean([ph.intergreen_s for ph in phases])) + float(
            np.mean(list(startup_lost.values()))
        )  # s per switch
        self.lost_per_switch_s = lost
        self.forfeited_veh = lost * s_ref / 3600.0
        super().__init__(
            junction_id, phases, lg, sat, g_min_s=G_MIN_THRESHOLD_S,
            threshold=self.forfeited_veh * s_ref,
        )  # fmt: skip


@dataclass(frozen=True)
class JunctionDesign:
    """What a signal plan is timed for, fixed when the scenario is built: the measured
    saturation flows and start-up losses of the INITIAL vehicle mix, and the Webster plan of the
    INITIAL demand. Like a real signal plan, it does not follow live changes of mix or demand;
    only a reset (a new build) recomputes it."""

    junction_id: str
    phases: list[Phase]
    sat: dict[str, float]
    startup_lost: dict[str, float]
    plan: WebsterPlan


def make_design(net, lg, routes, scenario) -> list[JunctionDesign]:
    """The design record of every signalised junction (empty for an uncontrolled scenario)."""
    from trafficsim.engine.calibration import saturation_flows, startup_lost_times
    from trafficsim.engine.webster import build_phases, movement_flows, webster_plan

    if scenario.signal_control == "uncontrolled":
        return []
    out = []
    for j in net.junctions:
        if j.control != "signalised":
            continue
        phases = build_phases(net, j)
        sat = saturation_flows(net, scenario.vehicle_mix, j.id)
        lost = startup_lost_times(net, scenario.vehicle_mix, j.id)
        flows = movement_flows(net, routes, lg, scenario.demand, j)
        out.append(
            JunctionDesign(j.id, phases, sat, lost, webster_plan(phases, flows, sat, lost, net))
        )
    return out


def make_controllers(design: list[JunctionDesign], policy: str, lg) -> list[SignalController]:
    """One controller per signalised junction for ``policy``, all from the design record."""
    out: list[SignalController] = []
    for d in design:
        if policy == "fixed_webster":
            out.append(FixedTimeWebster(d.junction_id, d.phases, lg, d.plan))
        elif policy == "max_pressure":
            out.append(MaxPressure(d.junction_id, d.phases, lg, d.sat))
        else:
            out.append(MaxPressureThreshold(d.junction_id, d.phases, lg, d.sat, d.startup_lost))
    return out
