"""Signal controllers for a signalised junction (approach-wise split phasing).

State machine per junction: GREEN(phase) → AMBER → ALL_RED → GREEN(next phase). Only
the green phase's connectors accept *new* entries; vehicles that committed before the
change keep their reservation (engine/gates.py), which is the amber dilemma-zone rule.

  FixedTimeWebster  cycles through the phases with Webster greens (engine/webster.py).
  MaxPressure       Varaiya (2013): pressure of a phase = Σ over its movements of
                    (queued upstream − queued downstream) × measured saturation flow;
                    after G_MIN the highest-pressure phase gets the green, a switch is
                    forced at G_MAX if another phase has queued vehicles.
Durations are kept in whole ticks so the controller is exact and deterministic.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.constants import STEPS_PER_SECOND
from trafficsim.engine.params.control import G_MAX_S, G_MIN_S, V_QUEUED_MPS
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
    def __init__(self, junction_id: str, phases: list[Phase], lg, plan: WebsterPlan) -> None:
        super().__init__(junction_id, phases, lg)
        self.plan = plan
        self.green = [_ticks(g) for g in plan.greens_s]

    def _decide(self, vs, lg) -> int | None:
        if self.elapsed >= self.green[self.phase]:
            return (self.phase + 1) % len(self.phases)
        return None


class MaxPressure(SignalController):
    def __init__(self, junction_id: str, phases: list[Phase], lg, sat: dict[str, float]):
        super().__init__(junction_id, phases, lg)
        self.g_min, self.g_max = _ticks(G_MIN_S), _ticks(G_MAX_S)
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
        if p[best] > p[self.phase]:
            return best
        if self.elapsed >= self.g_max and any(waiting[k] > 0 for k in others):
            return max((k for k in others if waiting[k] > 0), key=lambda k: p[k])
        return None


def make_controllers(net, lg, routes, scenario) -> list[SignalController]:
    """One controller per signalised junction, as chosen by the scenario."""
    from trafficsim.engine.calibration import saturation_flows
    from trafficsim.engine.webster import build_phases, movement_flows, webster_plan

    if scenario.signal_control == "uncontrolled":
        return []
    out: list[SignalController] = []
    for j in net.junctions:
        if j.control != "signalised":
            continue
        phases = build_phases(net, j)
        sat = saturation_flows(net, scenario.vehicle_mix, j.id)
        if scenario.signal_control == "fixed_webster":
            flows = movement_flows(net, routes, lg, scenario.demand, j)
            plan = webster_plan(phases, flows, sat, net)
            out.append(FixedTimeWebster(j.id, phases, lg, plan))
        else:
            out.append(MaxPressure(j.id, phases, lg, sat))
    return out
