"""Structural checks on a network: grade separation, vertical clearance, lane features.

These back the grade-separation invariant at the *topology and geometry* level: the only
way between level 0 (ground) and level 1 (flyover) is through a ramp, no junction turn
touches level 1, and wherever level-1 roadway lies above ground roadway the vertical
clearance (soffit to road surface) meets the minimum.
"""

from __future__ import annotations

import numpy as np

from trafficsim.network import geometry as geo
from trafficsim.network.types import Network, Road


def lane_counts(net: Network) -> set[int]:
    return {r.n_lanes for r in net.roads}


def exit_roads(net: Network) -> set[str]:
    return {z.exit_road for z in net.zones}


def dropped_lanes(net: Network) -> list[str]:
    """Lanes that end without a successor on a road that is not a network exit."""
    exits = exit_roads(net)
    return [
        ln.id for r in net.roads if r.id not in exits for ln in r.lanes if not net.successors(ln.id)
    ]


def grade_separation_violations(net: Network) -> list[str]:
    out: list[str] = []
    for c in net.connectors:
        ra, rb = net.road_of(c.from_lane), net.road_of(c.to_lane)
        if c.junction_id is not None and (ra.level or rb.level):
            out.append(f"{c.id}: junction connector touches the flyover level")
        if ra.level != rb.level:
            upper = ra if ra.level > rb.level else rb
            if upper.kind != "ramp":
                out.append(f"{c.id}: level change not via a ramp ({upper.id})")
        for r, other in ((ra, rb), (rb, ra)):
            if r.kind == "flyover" and other.kind not in ("flyover", "ramp"):
                out.append(f"{c.id}: flyover {r.id} connects directly to {other.id}")
    return out


def _distances_xy(points: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised xy distance from many points to a polyline, and the polyline's z there."""
    best_d = np.full(points.shape[0], np.inf)
    best_z = np.zeros(points.shape[0])
    for a, b in zip(p[:-1], p[1:], strict=True):
        ab = b[:2] - a[:2]
        t = np.clip(((points[:, :2] - a[:2]) @ ab) / (ab @ ab), 0.0, 1.0)
        proj = a[:2] + t[:, None] * ab
        d = np.sqrt(((points[:, :2] - proj) ** 2).sum(axis=1))
        better = d < best_d
        best_d[better] = d[better]
        best_z[better] = (a[2] + t * (b[2] - a[2]))[better]
    return best_d, best_z


def _footprint_samples(road: Road, step_m: float = 2.0) -> np.ndarray:
    """Points covering a road's surface: each lane's centre and both edges (inset 1 mm)."""
    pts = []
    for ln in road.lanes:
        n = max(2, int(np.ceil(ln.length_m / step_m)) + 1)
        for off in (-(ln.width_m / 2 - 1e-3), 0.0, ln.width_m / 2 - 1e-3):
            line = geo.offset_left(ln.centreline, off)
            seg = geo.segment_lengths(line)
            s = np.concatenate([[0.0], np.cumsum(seg)])
            q = np.linspace(0.0, s[-1], n)
            pts.append(np.column_stack([np.interp(q, s, line[:, i]) for i in range(3)]))
    return np.vstack(pts)


def clearance_violations(
    net: Network, deck_thickness_m: float, min_clearance_m: float
) -> list[str]:
    out: list[str] = []
    linked: dict[str, set[str]] = {}
    for c in net.connectors:
        a, b = net.lane(c.from_lane).road_id, net.lane(c.to_lane).road_id
        linked.setdefault(a, set()).add(b)
        linked.setdefault(b, set()).add(a)
    ground = [r for r in net.roads if r.level == 0]
    for upper in (r for r in net.roads if r.level == 1):
        pts = _footprint_samples(upper)
        for g in ground:
            if g.id in linked.get(upper.id, set()):
                continue  # shared endpoint at a diverge/merge, not an overpass
            for ln in g.lanes:
                d, z_below = _distances_xy(pts, ln.centreline)
                over = d < ln.width_m / 2
                if np.any(over):
                    gap = pts[over, 2] - deck_thickness_m - z_below[over]
                    if gap.min() < min_clearance_m - 1e-9:
                        out.append(f"{upper.id} over {ln.id}: clearance {gap.min():.2f} m")
        for j in net.junctions:
            x0, y0 = j.polygon[:, :2].min(axis=0)
            x1, y1 = j.polygon[:, :2].max(axis=0)
            inside = (pts[:, 0] > x0) & (pts[:, 0] < x1) & (pts[:, 1] > y0) & (pts[:, 1] < y1)
            if np.any(inside):
                gap = pts[inside, 2] - deck_thickness_m - j.polygon[0, 2]
                if gap.min() < min_clearance_m - 1e-9:
                    out.append(f"{upper.id} over {j.id}: clearance {gap.min():.2f} m")
    return out
