"""Junction entry control: spillback guard, conflict zones, give-way gaps, (signals).

Evaluated once per step for every vehicle approaching a junction connector, nearest to
the stop line first (deterministic). A vehicle may enter connector C if
  1. its signal permits (part 4; always true without a controller),
  2. spillback guard: the *guaranteed* room at the start of C's exit lane is at least
     the vehicle's own length + s0. Guaranteed room = distance from the lane start to
     where the rear of the last vehicle on that lane would come to rest if it braked
     now at its comfortable deceleration b (rear + v²/2b; just the rear for a standing
     queue), minus length + s0 of every vehicle that will enter that lane first (already
     on a connector into it, or committed and nearer its line). Moving traffic does not
     block entry; a queue does,
  3. on every connector conflicting with C (crossing paths or same exit lane) no vehicle
     is reserved, and every vehicle on it has its rear past the conflict point,
  4. for yielding movements (J2): every vehicle approaching on a conflicting priority
     movement is at least the critical gap (seconds, at its current speed) from the
     conflict point — where HCM measures critical headways.
Commitment: a permitted vehicle within its comfortable stopping distance plus one step
of travel plus the stop-line standoff reserves C. Reservations block conflicting
movements and claim exit-lane room until the vehicle enters, so a permission is never
revoked once the vehicle can no
longer stop comfortably — which is also the amber dilemma-zone rule for signals.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from trafficsim.engine.constants import DT
from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.leaders import Occupancy
from trafficsim.engine.params.control import (
    CRITICAL_GAP_MAJOR_RIGHT_S,
    CRITICAL_GAP_MINOR_LEFT_S,
    CRITICAL_GAP_MINOR_RIGHT_S,
    STOP_LINE_STANDOFF_M,
    V_QUEUED_MPS,
)
from trafficsim.engine.params.driving import LOOKAHEAD_M
from trafficsim.engine.vehicle import LEN, S0, A, B, VehicleState
from trafficsim.network.conflicts import conflict_table
from trafficsim.network.types import Network

# signal(conn_seg) -> True if the connector's signal currently allows NEW entries.
SignalCheck = Callable[[int], bool]


class JunctionGates:
    def __init__(self, net: Network, lg: LaneGraph) -> None:
        table = conflict_table(net)
        minor = {ln for j in net.junctions for ln in j.minor_approach_lanes}
        self.lg = lg
        self.conflicts: dict[int, set[int]] = {}
        self.conf_s: dict[int, dict[int, float]] = {}  # c -> {o: conflict point along o}
        self.priority_conflicts: dict[int, list[int]] = {}
        self.crit_gap: dict[int, float] = {}
        yields = {lg.seg_of[c.id]: c.yields for c in net.connectors if c.junction_id}
        major_lanes = {
            j.id: max(net.road_of(ln).n_lanes for ln in j.approach_lanes if ln not in minor)
            for j in net.junctions
        }
        for c in net.connectors:
            if c.junction_id is None:
                continue
            k = lg.seg_of[c.id]
            nl = major_lanes[c.junction_id]
            self.conf_s[k] = {lg.seg_of[o]: cf.s_other for o, cf in table[c.id].items()}
            self.conflicts[k] = set(self.conf_s[k])
            self.priority_conflicts[k] = sorted(o for o in self.conflicts[k] if not yields[o])
            if c.yields:
                if c.from_lane in minor:
                    gap_table = (
                        CRITICAL_GAP_MINOR_LEFT_S
                        if c.movement == "left"
                        else CRITICAL_GAP_MINOR_RIGHT_S
                    )
                else:
                    gap_table = CRITICAL_GAP_MAJOR_RIGHT_S
                self.crit_gap[k] = gap_table[nl]
        self.signal: SignalCheck | None = None
        self.reserved: dict[int, int] = {}  # vid -> connector segment
        self.permit: dict[int, bool] = {}  # row -> may enter its next connector
        self.room_seen: dict[int, tuple[float, float]] = {}  # vid -> (room, need) now
        self.commit_room: dict[int, tuple[float, float]] = {}  # vid -> at commitment
        # (vid, connector, accepted gap [s]) for every committed yielding movement
        self.accepted_gaps: list[tuple[int, int, float]] = []

    def __call__(self, i: int, conn: int) -> bool:
        return self.permit.get(i, True) if conn in self.conflicts else True

    def may_enter(self, vid: int, row: int, conn: int) -> bool:
        """Hard check at the moment of crossing the line (used by transfer)."""
        return self.reserved.get(vid) == conn or self.permit.get(row, False)

    def update(self, vs: VehicleState, occ: Occupancy) -> None:
        lg = self.lg
        self.permit = {}
        on_conn = lg.is_conn[vs.seg]
        self._rear_min = _rear_minima(vs, lg)
        room_cache: dict[int, float] = {}
        self._sig_cache: dict[int, bool] = {}
        live = dict(zip(vs.vid.tolist(), range(vs.n), strict=True))
        self.reserved = {
            v: c for v, c in self.reserved.items() if v in live and vs.nxt[live[v]] == c
        }
        need_all = LEN[vs.cls] + S0[vs.cls]
        claimed: dict[int, float] = {}
        for i in np.flatnonzero(on_conn):
            to = int(lg.conn_to[vs.seg[i]])
            claimed[to] = claimed.get(to, 0.0) + float(need_all[i])
        # Reservations claim room only for vehicles that will enter AFTER them: they are
        # added below while walking the candidates nearest-to-the-line first.

        nx = vs.nxt
        d = lg.length[vs.seg] - vs.s
        cand = (nx >= 0) & (d < LOOKAHEAD_M)
        cand[cand] &= lg.is_conn[nx[cand]]
        rows = np.flatnonzero(cand)
        rows = rows[np.lexsort((vs.vid[rows], d[rows]))]
        self._movers = _movers(vs, rows, d)
        res_conns = set(self.reserved.values())
        for i in rows:
            i = int(i)
            vid, c = int(vs.vid[i]), int(nx[i])
            to = int(lg.conn_to[c])
            need = float(need_all[i])
            mine = self.reserved.get(vid) == c
            if to not in room_cache:
                room_cache[to] = self._room(vs, occ, to)
            room = room_cache[to] - claimed.get(to, 0.0)
            self.room_seen[vid] = (room, need)
            if mine:
                self.permit[i] = True
                claimed[to] = claimed.get(to, 0.0) + need
                continue
            ok = self._allowed(c, room, need, res_conns)
            self.permit[i] = ok
            v, cl = float(vs.v[i]), int(vs.cls[i])
            commit = v * v / (2.0 * B[cl]) + v * DT + 0.5 * A[cl] * DT * DT
            commit += STOP_LINE_STANDOFF_M
            if ok and d[i] <= commit:
                self.reserved[vid] = c
                self.commit_room[vid] = (room, need)
                if c in self.crit_gap:
                    self.accepted_gaps.append((vid, c, self._gap(c)))
                res_conns.add(c)
                claimed[to] = claimed.get(to, 0.0) + need

    def _allowed(self, c: int, room: float, need: float, reserved: set[int]) -> bool:
        if self.signal is not None:
            if c not in self._sig_cache:
                self._sig_cache[c] = self.signal(c)
            if not self._sig_cache[c]:
                return False
        if room < need:
            return False
        for o, s_o in self.conf_s[c].items():
            if o in reserved or self._rear_min.get(o, np.inf) < s_o:
                return False  # someone on/committed to o has not cleared the conflict
        if c in self.crit_gap:  # yielding movement: gap acceptance against priority traffic
            return self._gap(c) >= self.crit_gap[c]
        return True

    def _gap(self, c: int) -> float:
        """Earliest arrival [s] of a moving priority vehicle at a conflict point with c."""
        best = np.inf
        for p in self.priority_conflicts[c]:
            s_p = self.conf_s[c][p]
            for d, v in self._movers.get(p, ()):
                best = min(best, (d + s_p) / v)
        return best

    def _room(self, vs: VehicleState, occ: Occupancy, lane: int) -> float:
        j = occ.first.get(lane)
        if j is None:
            return float(self.lg.length[lane])
        rear = float(occ.s[j] - occ.length[j])
        row = int(occ.row[j])
        if row < 0:  # incident: stationary
            return rear
        v = float(occ.v[j])
        return rear + v * v / (2.0 * float(B[vs.cls[row]]))


def _rear_minima(vs: VehicleState, lg: LaneGraph) -> dict[int, float]:
    """connector -> smallest rear position (along it) of any vehicle body still on it."""
    out: dict[int, float] = {}
    lens = LEN[vs.cls]
    for i in np.flatnonzero(lg.is_conn[vs.seg]):
        c = int(vs.seg[i])
        out[c] = min(out.get(c, np.inf), float(vs.s[i] - lens[i]))
    for i in np.flatnonzero(vs.tail >= 0):
        c = int(vs.tail[i])
        if lg.is_conn[c]:
            out[c] = min(out.get(c, np.inf), float(lg.length[c] + vs.s[i] - lens[i]))
    return out


def _movers(vs: VehicleState, rows: np.ndarray, d: np.ndarray) -> dict[int, list]:
    """connector -> [(distance to its line, speed)] of approaching vehicles that move."""
    out: dict[int, list] = {}
    for i in rows:
        v = float(vs.v[i])
        if v >= V_QUEUED_MPS:
            out.setdefault(int(vs.nxt[i]), []).append((float(d[i]), v))
    return out
