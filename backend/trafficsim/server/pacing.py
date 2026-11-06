"""Real-time pacing: how many fixed sim steps to run per WebSocket frame.

Speed k means k simulated seconds per wall-clock second, at any frame rate. With
STEPS_PER_SECOND = 10, a 1× session at 10 Hz runs exactly 1 step per frame; at 5 Hz it
runs 2; at 4 Hz it alternates 2, 3, 2, 3, ... (2.5 on average). The fractional remainder
is carried in an exact ``Fraction`` so the long-run ratio is exact, with no float drift.
"""

from __future__ import annotations

from fractions import Fraction

from trafficsim.engine.constants import STEPS_PER_SECOND


class StepPacer:
    def __init__(self, tick_hz: float) -> None:
        if tick_hz <= 0:
            raise ValueError("tick_hz must be positive")
        self._hz = Fraction(str(tick_hz))
        self._owed = Fraction(0)

    def steps_for_frame(self, speed: float) -> int:
        """Steps to run this frame for the requested speed (sim seconds per wall second)."""
        if speed < 0:
            raise ValueError("speed must be non-negative")
        self._owed += Fraction(str(speed)) * STEPS_PER_SECOND / self._hz
        n = int(self._owed)  # floor for non-negative values
        self._owed -= n
        return n
