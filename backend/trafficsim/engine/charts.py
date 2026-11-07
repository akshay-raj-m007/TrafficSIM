"""Measurements behind the results charts (read-only: nothing here touches the dynamics).

All three come from vehicle positions and speeds, none is estimated:

mfd    macroscopic fundamental diagram of the whole network, from Edie's generalised
       definitions over windows of ``MFD_WINDOW_S``: density k = total vehicle-time /
       (window x lane-length) and flow q = total vehicle-distance / (window x lane-length),
       lane-length = sum of the lengths of all open lane and connector segments, so both are
       per lane. Each point records whether the flyover was open at the end of its window (its lanes
       count in the lane-length only then).
speed  space-time speed field of four corridors (eastbound / westbound, surface route /
       flyover route): cells of ``CELL_M`` x 1 s, speed = total distance / total time of the
       vehicles in the cell (Edie, a space-mean speed). Distance is v x dt of the step.
queue  J1 and J2 longest approach queue every second (engine/queues.py).

History is kept for ``HISTORY_S``; a session asks for what it has not seen yet.
"""

from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass

import numpy as np

from trafficsim.engine.constants import DT, STEPS_PER_SECOND
from trafficsim.network.routing import fastest_route, grade_separated_roads

CELL_M = 10.0
MFD_WINDOW_S = 10.0
HISTORY_S = 600
NO_DATA = 255  # speed byte: 0.1 m/s units, 255 = no vehicle in the cell
J1_QUEUES, J2_QUEUES = ("J1_W", "J1_E", "J1_N", "J1_S"), ("J2_W", "J2_E", "J2_N")
DIRECTIONS = {"eastbound": ("W", "E"), "westbound": ("E", "W")}


@dataclass(frozen=True, slots=True)
class Corridor:
    key: str
    label: str
    roads: tuple[str, ...]
    length_m: float
    x0: np.ndarray  # corridor offset of the start of each segment (-1: not on the corridor)

    @property
    def cells(self) -> int:
        return max(1, int(np.ceil(self.length_m / CELL_M)))


def build_corridors(net, lg) -> list[Corridor]:
    """Surface and flyover route of each direction between the W and E zones."""
    zones = {z.id for z in net.zones}
    if not {"W", "E"} <= zones:
        return []
    fly = grade_separated_roads(net)
    out = []
    for dname, (o, d) in DIRECTIONS.items():
        for kind, closed in (("surface", fly), ("flyover", frozenset())):
            roads = fastest_route(net, o, d, closed)
            if not roads or (kind == "flyover" and not fly & set(roads)):
                continue
            x0 = np.full(lg.n, -1.0)
            at = 0.0
            for a, b in zip(roads, [*roads[1:], None], strict=True):
                for seg in lg.road_segs[a]:
                    x0[seg] = at
                at += float(lg.length[lg.road_segs[a][0]])
                if b is None:
                    break
                conns = [
                    k for k in range(lg.n)
                    if lg.is_conn[k] and lg.road_of[lg.conn_from[k]] == a
                    and lg.road_of[lg.conn_to[k]] == b
                ]  # fmt: skip
                for k in conns:
                    x0[k] = at
                at += float(np.mean([lg.length[k] for k in conns])) if conns else 0.0
            out.append(Corridor(f"{dname}_{kind}", f"{dname} {kind}", tuple(roads), at, x0))
    return out


class ChartMeter:
    def __init__(self, sim) -> None:
        self.sim = sim
        lg = sim.lg
        self.corridors = build_corridors(sim.network, lg)
        cells = [c.cells for c in self.corridors]
        self._base = np.concatenate([[0], np.cumsum(cells)]).astype(
            np.int64
        )  # corridor -> flat cell
        self._x0 = np.array([c.x0 for c in self.corridors]).reshape(len(cells), lg.n)
        self._last_cell = (np.array(cells) - 1)[:, None]
        self._flat_dist = np.zeros(int(self._base[-1]))
        self._flat_time = np.zeros(int(self._base[-1]))
        self._cols: deque[bytes] = deque(maxlen=HISTORY_S)  # one bytes per second: all corridors
        self.n_cols = 0  # columns finished so far (absolute index of the next one)
        self.mfd: deque[tuple[float, float, float, bool]] = deque(maxlen=HISTORY_S)
        self.n_mfd = 0
        self.queue: deque[tuple[float, float, float]] = deque(maxlen=HISTORY_S)
        self.n_queue = 0
        self._net_dist = self._net_time = 0.0
        fly = grade_separated_roads(sim.network)
        on_fly = np.array([(lg.road_of[k] in fly) or (lg.is_conn[k] and (
            lg.road_of[lg.conn_from[k]] in fly or lg.road_of[lg.conn_to[k]] in fly))
            for k in range(lg.n)], dtype=bool)  # fmt: skip
        self._lane_m_open = float(lg.length[~on_fly].sum())
        self._lane_m_fly = float(lg.length[on_fly].sum())

    def observe(self, vs, tick: int) -> None:
        """Accumulate this step (after the transfers), close the 1 s / 10 s windows."""
        if vs.n:
            d = vs.v * DT
            self._net_dist += float(d.sum())
            self._net_time += vs.n * DT
            if len(self.corridors):
                x0 = self._x0[:, vs.seg]  # (corridors, vehicles)
                on = x0 >= 0.0
                cell = ((x0 + vs.s[None, :]) / CELL_M).astype(np.int64)
                cell = np.clip(cell, 0, self._last_cell) + self._base[:-1, None]
                idx = cell[on]
                m = self._flat_dist.size
                self._flat_dist += np.bincount(
                    idx, weights=np.broadcast_to(d, on.shape)[on], minlength=m
                )
                self._flat_time += np.bincount(idx, minlength=m) * DT
        if tick % STEPS_PER_SECOND == 0:
            self._close_column()
        if tick % round(MFD_WINDOW_S * STEPS_PER_SECOND) == 0:
            self._close_mfd(tick / STEPS_PER_SECOND)

    def _close_column(self) -> None:
        t, dist = self._flat_time, self._flat_dist
        v = np.divide(dist, t, out=np.zeros_like(t), where=t > 0)
        col = np.where(t > 0, np.minimum(np.rint(v * 10.0), 254), NO_DATA).astype(np.uint8)
        self._flat_dist[:] = 0.0
        self._flat_time[:] = 0.0
        self._cols.append(col.tobytes())
        self.n_cols += 1

    def _close_mfd(self, t: float) -> None:
        lane_m = self._lane_m_open + (self._lane_m_fly if self.sim.flyover_open else 0.0)
        area = MFD_WINDOW_S * lane_m
        k = self._net_time / area * 1000.0  # veh / km / lane
        q = self._net_dist / area * 3600.0  # veh / h / lane
        self._net_dist = self._net_time = 0.0
        self.mfd.append((t, round(k, 3), round(q, 1), self.sim.flyover_open))
        self.n_mfd += 1

    def sample_queues(self, t: float, lengths: dict[str, float]) -> None:
        j1 = max((lengths[a] for a in J1_QUEUES if a in lengths), default=0.0)
        j2 = max((lengths[a] for a in J2_QUEUES if a in lengths), default=0.0)
        self.queue.append((t, round(j1, 1), round(j2, 1)))
        self.n_queue += 1

    def since(self, seen: dict) -> dict:
        """What a session has not seen yet; ``seen`` holds its cursors and is updated."""
        n_c = min(self.n_cols - seen.get("col", 0), len(self._cols))
        cols = list(self._cols)[len(self._cols) - n_c :] if n_c else []
        n_m = min(self.n_mfd - seen.get("mfd", 0), len(self.mfd))
        n_q = min(self.n_queue - seen.get("q", 0), len(self.queue))
        msg = {
            "col0": self.n_cols - n_c, "cell_m": CELL_M,
            "corridors": [{"key": c.key, "label": c.label, "cells": c.cells,
                           "length_m": round(c.length_m, 1)} for c in self.corridors],
            "speed_unit_mps": 0.1, "no_data": NO_DATA,
            "cols": [base64.b64encode(c).decode("ascii") for c in cols],
            "mfd": [list(p) for p in list(self.mfd)[len(self.mfd) - n_m :]] if n_m else [],
            "queue": [list(p) for p in list(self.queue)[len(self.queue) - n_q :]] if n_q else [],
        }  # fmt: skip
        seen.update(col=self.n_cols, mfd=self.n_mfd, q=self.n_queue)
        return msg
