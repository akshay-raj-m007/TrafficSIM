"""Fixed simulation constants.

The time step is fixed for every scenario and is decoupled from the render frame rate:
the renderer interpolates between simulation states. The clock is kept as an integer
tick count; simulated time is derived as ``tick / STEPS_PER_SECOND`` so it is exact and
never accumulates floating-point error.
"""

from typing import Final

STEPS_PER_SECOND: Final[int] = 10
DT: Final[float] = 1.0 / STEPS_PER_SECOND  # 0.1 s

# Gravitational acceleration [m/s^2], used for grade resistance on ramps (step 2).
G: Final[float] = 9.81


def ticks_for(duration_s: float) -> int:
    """Number of whole steps in ``duration_s``. Rejects non-multiples of DT."""
    ticks = round(duration_s * STEPS_PER_SECOND)
    if abs(ticks - duration_s * STEPS_PER_SECOND) > 1e-9:
        raise ValueError(f"duration {duration_s}s is not a multiple of DT={DT}s")
    if ticks < 0:
        raise ValueError("duration must be non-negative")
    return ticks


def time_of(tick: int) -> float:
    """Exact simulated time [s] at a given tick (division gives the nearest double)."""
    return tick / STEPS_PER_SECOND
