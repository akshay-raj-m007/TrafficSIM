"""Conflicts between junction turn paths, derived purely from geometry.

Two connectors of the same junction conflict if
  * they end in the same exit lane (merge conflict; conflict point = both path ends), or
  * their paths cross in plan view (crossing conflict; conflict point = the crossing).
Connectors that only share an approach lane (diverging movements) do not conflict:
vehicles on them are ordered by ordinary car-following in that lane.

For each conflict we store the arc length of the conflict point along *each* path, so
the engine can time a priority vehicle's arrival at the conflict point (that is where
HCM measures critical headways) and release a conflict once a vehicle's rear has
cleared it.
"""

from __future__ import annotations

from itertools import combinations
from typing import NamedTuple

import numpy as np

from trafficsim.network.types import Connector, Network

_EPS = 1e-9


class Conflict(NamedTuple):
    kind: str  # "merge" | "cross"
    s_self: float  # conflict point along this connector [m]
    s_other: float  # conflict point along the other connector [m]


def _cum(p: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.sqrt((np.diff(p, axis=0) ** 2).sum(1)))])


def crossing(p: np.ndarray, q: np.ndarray) -> tuple[float, float] | None:
    """Arc lengths (along p, along q) of the first proper xy crossing, or None."""
    sp, sq = _cum(p), _cum(q)
    for i in range(len(p) - 1):
        a0, a1 = p[i, :2], p[i + 1, :2]
        r = a1 - a0
        for j in range(len(q) - 1):
            b0, b1 = q[j, :2], q[j + 1, :2]
            s = b1 - b0
            den = r[0] * s[1] - r[1] * s[0]
            if abs(den) < _EPS:
                continue
            w = b0 - a0
            t = (w[0] * s[1] - w[1] * s[0]) / den
            u = (w[0] * r[1] - w[1] * r[0]) / den
            if _EPS < t < 1 - _EPS and _EPS < u < 1 - _EPS:
                return sp[i] + t * (sp[i + 1] - sp[i]), sq[j] + u * (sq[j + 1] - sq[j])
    return None


def conflict_between(a: Connector, b: Connector) -> Conflict | None:
    if a.junction_id is None or a.junction_id != b.junction_id or a.id == b.id:
        return None
    if a.to_lane == b.to_lane:
        return Conflict("merge", a.length_m, b.length_m)
    if a.from_lane == b.from_lane:
        return None
    x = crossing(a.path, b.path)
    return None if x is None else Conflict("cross", x[0], x[1])


def conflict_table(net: Network) -> dict[str, dict[str, Conflict]]:
    """connector id -> {conflicting connector id: Conflict as seen from the first}."""
    conns = [c for c in net.connectors if c.junction_id is not None]
    table: dict[str, dict[str, Conflict]] = {c.id: {} for c in conns}
    for a, b in combinations(conns, 2):
        k = conflict_between(a, b)
        if k:
            table[a.id][b.id] = k
            table[b.id][a.id] = Conflict(k.kind, k.s_other, k.s_self)
    return table
