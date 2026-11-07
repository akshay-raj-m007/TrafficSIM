"""Alternation at a merge: connectors that lead into the same exit lane take turns by green.

Found by the surface-lane experiment with the flyover closed: J1's two through lanes both
enter the single link lane east of J1. Entry goes to the vehicle nearest its stop line and a
granted vehicle reserves its connector, which blocks the other connector (same exit lane); the
next vehicle of the first lane has reached the line when the reservation ends, so the second
lane was never served again after the first green (0 veh/h from a queue of 65 vehicles while
the other lane was served every cycle).

Rule (deterministic, no new parameter). Per exit lane, a *green* is a period in which the set of
connectors into it that the signal allows stays the same. The first connector granted entry in a
green *owns* it: the others yield while the owner still has a vehicle queued at its line (the
queue definition of engine/queues.py). At the start of a green, before anyone has been granted,
the connector that owned the previous green yields to a rival with a queued vehicle. So queues
are served in turn, green by green, and a green is not broken into single-vehicle handovers
(each handover waits for the merge point to clear, which cut the discharge to under half).
Without signals there is no green: the rule is off. Only connectors that do not yield to
priority traffic take part (J2's minor approach has its own gap rule and must never make the
major road wait).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.params.control import V_QUEUED_MPS
from trafficsim.engine.queues import QUEUE_MAX_GAP_M


class MergeTurns:
    def __init__(self, lg: LaneGraph, yielding: set[int]) -> None:
        by_exit: dict[int, list[int]] = defaultdict(list)
        for c in range(lg.n):
            if lg.is_conn[c] and lg.junction_of[c] and c not in yielding:
                by_exit[int(lg.conn_to[c])].append(c)
        self.groups = {to: tuple(cs) for to, cs in by_exit.items() if len(cs) > 1}
        self.rivals = {c: tuple(o for o in cs if o != c) for cs in self.groups.values() for c in cs}
        self.allowed: dict[int, frozenset[int]] = {}  # exit lane -> connectors the signal allows
        self.owner: dict[int, int | None] = {}  # exit lane -> owner of the current green
        # (exit lane, allowed set) -> owner of the previous green with that same allowed set (a
        # green of another phase, e.g. the cross street, is not this lane's previous turn)
        self.previous: dict[tuple[int, frozenset[int]], int] = {}
        self.queued: set[int] = set()

    def observe(self, v, d, nxt, rows, signal_ok: Callable[[int], bool] | None) -> None:
        """Connectors with a vehicle queued at the line; start a new green when the allowed set
        of an exit lane changes."""
        self.queued = {int(nxt[i]) for i in rows if v[i] < V_QUEUED_MPS and d[i] <= QUEUE_MAX_GAP_M}
        if signal_ok is None:
            return
        for to, cs in self.groups.items():
            now = frozenset(c for c in cs if signal_ok(c))
            before = self.allowed.get(to)
            if now != before:
                if self.owner.get(to) is not None and before:
                    self.previous[(to, before)] = self.owner[to]  # type: ignore[assignment]
                self.allowed[to] = now
                self.owner[to] = None

    def must_yield(self, c: int, to: int) -> bool:
        if to not in self.allowed:  # no signals, or not a merge
            return False
        waiting = [o for o in self.rivals.get(c, ()) if o in self.queued and o in self.allowed[to]]
        owner = self.owner.get(to)
        if owner is None:  # nobody granted yet in this green: last green's owner goes second
            return bool(waiting) and self.previous.get((to, self.allowed[to])) == c
        return owner != c and owner in self.queued and owner in self.allowed[to]

    def granted(self, c: int, to: int) -> None:
        if to in self.groups and self.owner.get(to) is None:
            self.owner[to] = c
