"""Detector lines: count front-bumper crossings at a fixed position along a road.

A detector covers *every lane* of its road at arc length ``s_m``. A vehicle is counted at
the step in which its front goes from before the line to on/after it, evaluated on the
vehicle's own lane segment before segment transfers. Lane changes keep the arc position,
so no vehicle can be counted twice or skipped; detectors are kept at least
DETECTOR_MIN_END_CLEARANCE_M from both road ends, so no step can carry a vehicle across a
road boundary and over the line at once. Flow = crossings in the last
DETECTOR_WINDOW_S seconds, scaled to veh/h (so one vehicle = 60 veh/h at 60 s).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.params.control import DETECTOR_MIN_END_CLEARANCE_M, DETECTOR_WINDOW_S
from trafficsim.engine.vehicle import VehicleState


@dataclass(frozen=True, slots=True)
class DetectorSpec:
    id: str
    label: str
    road_id: str
    s_m: float


class Detectors:
    def __init__(self, lg: LaneGraph, specs: tuple[DetectorSpec, ...]) -> None:
        self.specs = specs
        self.line = np.full((len(specs), lg.n), np.inf)  # detector x segment -> line position
        for k, sp in enumerate(specs):
            for seg in lg.road_segs[sp.road_id]:
                length = float(lg.length[seg])
                lo, hi = DETECTOR_MIN_END_CLEARANCE_M, length - DETECTOR_MIN_END_CLEARANCE_M
                if not lo <= sp.s_m <= hi:
                    raise ValueError(
                        f"detector {sp.id}: s = {sp.s_m} m must lie in [{lo}, {hi:.1f}] on "
                        f"{lg.ids[seg]}"
                    )
                self.line[k, seg] = sp.s_m
        self.total = np.zeros(len(specs), dtype=np.int64)
        self._times: list[deque[float]] = [deque() for _ in specs]

    def observe(self, vs: VehicleState, s_before: np.ndarray, t_now: float) -> None:
        """Count crossings between ``s_before`` and ``vs.s`` (call before segment transfers)."""
        if vs.n == 0 or not self.specs:
            return
        line = self.line[:, vs.seg]  # (detectors, vehicles)
        crossed = (s_before[None, :] < line) & (vs.s[None, :] >= line)
        for k in np.flatnonzero(crossed.any(axis=1)):
            n = int(crossed[k].sum())
            self.total[k] += n
            self._times[k].extend([t_now] * n)

    def window_count(self, k: int, t_now: float) -> int:
        q = self._times[k]
        while q and q[0] <= t_now - DETECTOR_WINDOW_S:
            q.popleft()
        return len(q)

    def flow_veh_per_h(self, k: int, t_now: float) -> float:
        """Flow over the last window (the elapsed time if the run is younger than it)."""
        span = min(DETECTOR_WINDOW_S, t_now)
        return self.window_count(k, t_now) * 3600.0 / span if span > 0 else 0.0
