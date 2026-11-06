"""What a live session simulates: seed, signal control, demand scale.

Step 2b exposes these only as WebSocket query parameters (an experiment seam for the
measurement tools and the later scenario controls); the UI has no controls for them yet.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, get_args

from trafficsim.engine.presets import DEMO_DEMAND, scaled
from trafficsim.engine.scenario import Scenario, SignalControl

SESSION_DURATION_S: Final[float] = 3600.0  # simulated length of a live session [s]
DEMAND_SCALE_RANGE: Final[tuple[float, float]] = (0.25, 3.0)
MAX_SEED: Final[int] = 2**32 - 1
DEFAULT_SIGNAL: Final[str] = "fixed_webster"


@dataclass(frozen=True)
class SessionParams:
    seed: int = 42
    signal: str = DEFAULT_SIGNAL
    demand_scale: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.seed <= MAX_SEED:
            raise ValueError(f"seed must be in [0, {MAX_SEED}]")
        if self.signal not in get_args(SignalControl):
            raise ValueError(f"signal must be one of {get_args(SignalControl)}")
        lo, hi = DEMAND_SCALE_RANGE
        if not lo <= self.demand_scale <= hi:
            raise ValueError(f"demand_scale must be in [{lo}, {hi}]")

    def with_seed(self, seed: int) -> SessionParams:
        return replace(self, seed=seed)

    def scenario(self) -> Scenario:
        return Scenario(
            seed=self.seed,
            duration_s=SESSION_DURATION_S,
            demand=scaled(DEMO_DEMAND, self.demand_scale),
            signal_control=self.signal,  # type: ignore[arg-type]
        )
