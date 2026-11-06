"""Move vehicles across segment ends; remove vehicles that complete their route.

A vehicle whose front passes the end of its segment continues on its cached next
segment (``nxt``). It keeps a *tail* reference to the segment it left until its rear has
cleared it (see leaders.py ghosts). Passing the end of a segment with no valid way on is
impossible by construction (a stationary obstacle sits there); if it ever happens the
engine raises instead of silently repositioning the vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.routes import NEXT_EXIT, RouteTable, next_seg, refresh_lane_cache
from trafficsim.engine.vehicle import LEN, VehicleState


class EngineInvariantError(RuntimeError):
    """A physical invariant was violated; the run is invalid."""


@dataclass
class ExitRecord:
    vid: int
    cls: int
    route: int
    t_gen: float
    t_ins: float
    t_exit: float


@dataclass(frozen=True, slots=True)
class LaneChangeEvent:
    t: float
    vid: int
    from_seg: int
    to_seg: int
    mandatory: bool
    gap_lead: float  # accepted gap to the new leader [m]
    gap_lag: float  # accepted gap of the new follower [m] (inf: none)
    a_follower: float  # new follower's IDM acceleration right after the change [m/s²]
    b_safe: float  # acceptance threshold that applied [m/s²]


@dataclass
class TransferLog:
    exits: list[ExitRecord] = field(default_factory=list)
    # (vid, connector segment, time) for every junction entry, for the spillback tests
    junction_entries: list[tuple[int, int, float]] = field(default_factory=list)
    lane_changes: list[LaneChangeEvent] = field(default_factory=list)


def advance_segments(
    vs: VehicleState, lg: LaneGraph, rt: RouteTable, t_now: float, log: TransferLog
) -> list[int]:
    """Apply segment transitions in place; returns rows that entered a junction connector."""
    over = vs.s > lg.length[vs.seg]
    leaving = over & (vs.nxt == NEXT_EXIT)
    if np.any(leaving):
        for i in np.flatnonzero(leaving):
            log.exits.append(
                ExitRecord(
                    int(vs.vid[i]), int(vs.cls[i]), int(vs.route[i]),
                    float(vs.t_gen[i]), float(vs.t_ins[i]), t_now,
                )
            )  # fmt: skip
        vs.keep(~leaving)
    entered: list[int] = []
    for i in np.flatnonzero(vs.s > lg.length[vs.seg]):
        while vs.s[i] > lg.length[vs.seg[i]]:
            nx = int(vs.nxt[i])
            if nx < 0:
                raise EngineInvariantError(
                    f"vehicle {vs.vid[i]} ran past the end of {lg.ids[vs.seg[i]]} (nxt={nx})"
                )
            vs.s[i] -= lg.length[vs.seg[i]]
            vs.tail[i] = vs.seg[i]
            vs.seg[i] = nx
            if lg.is_conn[nx]:
                entered.append(int(i))
                log.junction_entries.append((int(vs.vid[i]), nx, t_now))
            else:
                vs.rpos[i] += 1
            vs.nxt[i] = next_seg(lg, rt, int(vs.route[i]), int(vs.rpos[i]), nx)
            refresh_lane_cache(vs, lg, rt, int(i))
    cleared = vs.s >= LEN[vs.cls]
    vs.tail[cleared] = -1
    return entered
