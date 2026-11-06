"""Compile a static ``Network`` into flat per-segment arrays for the engine.

A *segment* is something a vehicle can be on: every lane, and every junction connector
(turn path with real length). Zero-length lane-to-lane links (diverge, merge, lane drop,
widening) are not segments; they become successor edges between lane segments.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trafficsim.engine.params.driving import (
    A_LAT_COMFORT_MPS2,
    LANE_WIDTH_REF_M,
    LANE_WIDTH_SPEED_FRACTION_PER_M,
)
from trafficsim.engine.vehicle import MAX_VEHICLE_LENGTH_M, V0
from trafficsim.network.types import Network


def min_turn_radius(path: np.ndarray) -> float:
    """Smallest circumradius over consecutive point triples of a path (xy) [m]."""
    p = path[:, :2]
    a, b, c = p[:-2], p[1:-1], p[2:]
    ab = np.sqrt(((b - a) ** 2).sum(1))
    bc = np.sqrt(((c - b) ** 2).sum(1))
    ca = np.sqrt(((a - c) ** 2).sum(1))
    cross = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0])
    with np.errstate(divide="ignore"):
        r = np.where(cross > 1e-12, ab * bc * ca / (2.0 * cross), np.inf)
    return float(r.min()) if r.size else float("inf")


def sin_theta_profile(line: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """(s at piece midpoints, sinθ = dz/ds per piece) or None for a level segment."""
    d = np.diff(line, axis=0)
    ds = np.sqrt((d**2).sum(1))
    if np.all(np.abs(d[:, 2]) < 1e-12):
        return None
    s_mid = np.cumsum(ds) - ds / 2.0
    return s_mid, d[:, 2] / ds


@dataclass(eq=False)
class LaneGraph:
    ids: list[str]
    length: np.ndarray  # [m]
    vlimit: np.ndarray  # speed limit, incl. curvature limit on turns [m/s]
    width: np.ndarray  # [m]
    is_conn: np.ndarray  # bool: junction connector
    road_of: list[str | None]  # road id of a lane segment (None for connectors)
    lane_index: np.ndarray  # lane index within its road (-1 for connectors)
    junction_of: list[str | None]
    conn_to: np.ndarray  # connector -> exit-lane segment (-1 for lanes)
    conn_from: np.ndarray  # connector -> approach-lane segment (-1 for lanes)
    succ: list[list[int]]
    succ_road: list[list[str]]  # road each successor leads to
    road_segs: dict[str, list[int]]  # road id -> lane segments by lane index
    profiles: dict[int, tuple[np.ndarray, np.ndarray]]  # graded segments
    v0_eff: np.ndarray  # (n_seg, n_class) effective desired speed [m/s]
    seg_of: dict[str, int]
    nbr: np.ndarray  # (n_seg, 2): adjacent lane segment [lower index, higher index] or -1
    ends_at_junction: np.ndarray  # bool: lane whose successors are junction connectors
    pred: list[list[int]]  # predecessor segments

    @property
    def n(self) -> int:
        return len(self.ids)


def compile_network(net: Network) -> LaneGraph:
    ids: list[str] = []
    seg_of: dict[str, int] = {}
    lengths, vlim, widths, road_of, lane_idx, junc = [], [], [], [], [], []
    road_segs: dict[str, list[int]] = {}
    profiles: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for r in net.roads:
        road_segs[r.id] = []
        for ln in r.lanes:
            k = len(ids)
            ids.append(ln.id)
            seg_of[ln.id] = k
            road_segs[r.id].append(k)
            lengths.append(ln.length_m)
            vlim.append(r.speed_limit_mps)
            widths.append(ln.width_m)
            road_of.append(r.id)
            lane_idx.append(ln.index)
            junc.append(None)
            prof = sin_theta_profile(ln.centreline)
            if prof is not None:
                profiles[k] = prof
    junction_conns = [c for c in net.connectors if c.junction_id is not None]
    for c in junction_conns:
        k = len(ids)
        ids.append(c.id)
        seg_of[c.id] = k
        a, b = net.road_of(c.from_lane), net.road_of(c.to_lane)
        v_curve = float(np.sqrt(A_LAT_COMFORT_MPS2 * min_turn_radius(c.path)))
        lengths.append(c.length_m)
        vlim.append(min(a.speed_limit_mps, b.speed_limit_mps, v_curve))
        widths.append(net.lane(c.from_lane).width_m)
        road_of.append(None)
        lane_idx.append(-1)
        junc.append(c.junction_id)

    n = len(ids)
    succ: list[list[int]] = [[] for _ in range(n)]
    succ_road: list[list[str]] = [[] for _ in range(n)]
    conn_to = np.full(n, -1, dtype=np.int32)
    conn_from = np.full(n, -1, dtype=np.int32)
    for c in net.connectors:
        a = seg_of[c.from_lane]
        to_road = net.lane(c.to_lane).road_id
        if c.junction_id is None:
            succ[a].append(seg_of[c.to_lane])
        else:
            k = seg_of[c.id]
            succ[a].append(k)
            succ[k].append(seg_of[c.to_lane])
            succ_road[k].append(to_road)
            conn_to[k], conn_from[k] = seg_of[c.to_lane], a
        succ_road[a].append(to_road)

    length = np.array(lengths)
    if length.min() < MAX_VEHICLE_LENGTH_M:
        bad = ids[int(length.argmin())]
        raise ValueError(f"segment {bad} is shorter than the longest vehicle")
    width = np.array(widths)
    vlimit = np.array(vlim)
    is_conn = np.array([r is None for r in road_of])
    # The lane-width model is a link (free-flow) effect; inside junction turns the
    # curvature limit sqrt(a_lat·R) governs instead, so connectors get no width reduction.
    factor = 1.0 - LANE_WIDTH_SPEED_FRACTION_PER_M * np.maximum(0.0, LANE_WIDTH_REF_M - width)
    factor[is_conn] = 1.0
    v0_eff = np.minimum(V0[None, :], vlimit[:, None]) * factor[:, None]
    if np.any(v0_eff <= 0):
        raise ValueError("lane-width model gives a non-positive desired speed")
    nbr = np.full((n, 2), -1, dtype=np.int32)
    for segs in road_segs.values():
        for k, sg in enumerate(segs):
            nbr[sg, 0] = segs[k - 1] if k > 0 else -1
            nbr[sg, 1] = segs[k + 1] if k + 1 < len(segs) else -1
    pred: list[list[int]] = [[] for _ in range(n)]
    for a in range(n):
        for b in succ[a]:
            pred[b].append(a)
    is_c = [r is None for r in road_of]
    ends_at_junction = np.array([any(is_c[b] for b in succ[a]) for a in range(n)])
    return LaneGraph(
        ends_at_junction=ends_at_junction,
        nbr=nbr,
        pred=pred,
        ids=ids,
        length=length,
        vlimit=vlimit,
        width=width,
        is_conn=is_conn,
        road_of=road_of,
        lane_index=np.array(lane_idx, dtype=np.int32),
        junction_of=junc,
        conn_to=conn_to,
        conn_from=conn_from,
        succ=succ,
        succ_road=succ_road,
        road_segs=road_segs,
        profiles=profiles,
        v0_eff=v0_eff,
        seg_of=seg_of,
    )
