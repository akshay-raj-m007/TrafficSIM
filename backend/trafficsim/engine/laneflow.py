"""Measured flow per lane and junction connector (the "Lane flow" overlay of the 3D view).

A vehicle *arrives* on a segment at the step it is first seen there: by insertion, by a link or
junction connector, or by a lane change. Per segment the meter reports arrivals over the last
``LANE_FLOW_WINDOW_S`` seconds scaled to veh/h (the elapsed time while the run is younger than
the window). A lane change counts as an arrival on the lane moved to; a vehicle that stays on a
segment is counted once. The window is 5 minutes, not the detectors' 60 s: a lane carrying
56 veh/h has no arrival in a given 60 s with probability 40 % (Poisson, exp(-0.93)), so a
60 s window would show low-flow lanes as "unused" at random; over 300 s that happens with
probability 0.9 %.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.constants import STEPS_PER_SECOND

LANE_FLOW_WINDOW_S = 300.0  # [s] see the module docstring
WINDOW_STEPS = round(LANE_FLOW_WINDOW_S * STEPS_PER_SECOND)


class LaneFlow:
    def __init__(self, n_segments: int) -> None:
        self.n = n_segments
        self._ring = np.zeros((WINDOW_STEPS, n_segments), dtype=np.int32)
        self._last = np.full(1024, -1, dtype=np.int64)  # last segment seen per vehicle id

    def observe(self, vs, tick: int) -> None:
        """Count this step's arrivals (call after the segment transfers of the step)."""
        row = self._ring[tick % WINDOW_STEPS]
        row[:] = 0
        if vs.n == 0:
            return
        top = int(vs.vid.max())
        if top >= self._last.size:
            grown = np.full(max(top + 1, 2 * self._last.size), -1, dtype=np.int64)
            grown[: self._last.size] = self._last
            self._last = grown
        moved = self._last[vs.vid] != vs.seg
        self._last[vs.vid] = vs.seg
        if moved.any():
            row += np.bincount(vs.seg[moved], minlength=self.n).astype(np.int32)

    def veh_per_h(self, t_now: float) -> list[int]:
        """Arrivals per segment over the last window, as veh/h."""
        span = min(LANE_FLOW_WINDOW_S, t_now)
        if span <= 0.0:
            return [0] * self.n
        return [int(round(x)) for x in self._ring.sum(axis=0) * (3600.0 / span)]
