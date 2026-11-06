"""Queue length at junction approaches, measured from actual vehicle positions.

On each approach lane the queue is the unbroken chain of queued vehicles that starts at
the stop line:
  * a vehicle is *queued* if its speed is below V_QUEUED_MPS (HCM queued-state threshold,
    5 mi/h);
  * the first queued vehicle must have its front within QUEUE_MAX_GAP_M of the line and
    each further one within QUEUE_MAX_GAP_M of the rear of the vehicle ahead.
QUEUE_MAX_GAP_M is derived, not fitted: the largest IDM equilibrium gap a vehicle keeps
while crawling at the queued-state speed, s0_max + V_QUEUED_MPS · T_max (the truck class).
Queue length = distance from the stop line to the rear of the last vehicle in the chain;
the count is the number of vehicles in it. Per approach: the number is summed over lanes
and the length is the longest lane's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.params.control import V_QUEUED_MPS
from trafficsim.engine.vehicle import LEN, S0, T, VehicleState

QUEUE_MAX_GAP_M = float(S0.max() + V_QUEUED_MPS * T.max())  # 3.0 + 2.2 * 1.8 = 7.0 m


@dataclass(frozen=True, slots=True)
class ApproachSpec:
    id: str
    label: str
    road_id: str  # the approach road; its lanes end at the stop / yield line


class QueueMeter:
    def __init__(self, lg: LaneGraph, specs: tuple[ApproachSpec, ...]) -> None:
        self.lg = lg
        self.specs = specs

    def measure(self, vs: VehicleState) -> list[tuple[int, float]]:
        """(vehicles in queue, queue length [m]) for each approach, from raw positions."""
        out = []
        lens = LEN[vs.cls]
        for sp in self.specs:
            n_tot, length_max = 0, 0.0
            for seg in self.lg.road_segs[sp.road_id]:
                rows = np.flatnonzero(vs.seg == seg)
                rows = rows[np.argsort(-vs.s[rows])]  # nearest the line first
                rear = float(self.lg.length[seg])
                n = 0
                for i in rows:
                    if vs.v[i] < V_QUEUED_MPS and rear - vs.s[i] <= QUEUE_MAX_GAP_M:
                        n += 1
                        rear = float(vs.s[i] - lens[i])
                    else:
                        break
                n_tot += n
                length_max = max(length_max, float(self.lg.length[seg]) - rear if n else 0.0)
            out.append((n_tot, length_max))
        return out
