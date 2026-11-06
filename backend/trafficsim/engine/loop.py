"""The simulation loop: advances a fixed time step DT = 0.1 s.

Step 1 (baseline) only advances the clock. The phase order inside ``step`` is fixed
now so later phases slot in without changing the loop contract:

    1. signals     update controller states            (step 2)
    2. demand      spawn vehicles / count unserved      (step 2)
    3. decisions   MOBIL lane changes, junction entry   (step 2)
    4. dynamics    IDM accelerations, ballistic update  (step 2)
    5. transfer    move vehicles across lane ends       (step 2)
    6. measure     detectors, queues, travel times      (step 2)
    7. clock       tick += 1

The engine has no notion of wall-clock time: real-time pacing is the server's job.
"""

from __future__ import annotations

from trafficsim.engine.constants import DT, time_of
from trafficsim.engine.rng import RngStreams
from trafficsim.engine.scenario import Scenario
from trafficsim.engine.vehicle import VehicleState
from trafficsim.network.types import Network


class Simulation:
    dt: float = DT

    def __init__(self, network: Network, scenario: Scenario) -> None:
        self.network = network
        self.scenario = scenario
        self.rng = RngStreams(scenario.seed)
        self.vehicles = VehicleState.empty()
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

    # ------------------------------------------------------------- stepping
    def step(self) -> bool:
        """Advance one DT. Returns False (and does nothing) once the scenario has ended."""
        if self.done:
            return False
        # Phases 1-6 are added in step 2 (see module docstring).
        self.tick += 1
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
