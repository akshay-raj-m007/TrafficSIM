"""Polyline geometry in metres (x east, y north, z up). Pure NumPy.

Offsets are lateral (in the xy plane) and use miter joins, so every offset segment is
exactly parallel to its source segment at exactly the requested distance — this is what
makes "1 unit = 1 metre" hold for lane widths on curves as well as straights.
"""

from __future__ import annotations

import numpy as np


def polyline(points: np.ndarray | list) -> np.ndarray:
    p = np.asarray(points, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or p.shape[0] < 2:
        raise ValueError(f"expected (N>=2, 3) points, got {p.shape}")
    return p


def segment_lengths(p: np.ndarray) -> np.ndarray:
    return np.sqrt((np.diff(p, axis=0) ** 2).sum(axis=1))


def arc_length(p: np.ndarray) -> float:
    return float(segment_lengths(p).sum())


def left_miter_normals(p: np.ndarray) -> np.ndarray:
    """Per-vertex xy offset vectors for a unit left offset (miter-scaled at joints)."""
    d = np.diff(p[:, :2], axis=0)
    seg_len = np.sqrt((d**2).sum(axis=1))
    if np.any(seg_len <= 0):
        raise ValueError("polyline has a zero-length xy segment")
    d = d / seg_len[:, None]
    seg_n = np.column_stack([-d[:, 1], d[:, 0]])  # rotate +90°: left of travel
    n = np.empty((p.shape[0], 2))
    n[0], n[-1] = seg_n[0], seg_n[-1]
    if p.shape[0] > 2:
        m = seg_n[:-1] + seg_n[1:]
        m_len = np.sqrt((m**2).sum(axis=1))
        if np.any(m_len < 1e-9):
            raise ValueError("polyline reverses direction")
        m = m / m_len[:, None]
        cos_half = (m * seg_n[1:]).sum(axis=1)
        n[1:-1] = m / cos_half[:, None]
    return n


def offset_left(p: np.ndarray, distance: float) -> np.ndarray:
    """Offset a polyline laterally by ``distance`` metres to the left of travel."""
    q = np.array(p, dtype=np.float64, copy=True)
    q[:, :2] += left_miter_normals(p) * distance
    return q


def straight(x0: float, y0: float, x1: float, y1: float, z: float = 0.0) -> np.ndarray:
    return np.array([[x0, y0, z], [x1, y1, z]], dtype=np.float64)


def graded(
    x0: float, y0: float, x1: float, y1: float, z0: float, z1: float, step_m: float = 5.0
) -> np.ndarray:
    """Straight-in-plan line whose elevation follows a smoothstep vertical curve.

    z(u) = z0 + (z1 - z0) * (3u^2 - 2u^3): zero grade at both ends, peak grade
    1.5 * |z1 - z0| / L at mid-length.
    """
    plan_len = float(np.hypot(x1 - x0, y1 - y0))
    n = max(2, int(np.ceil(plan_len / step_m)) + 1)
    u = np.linspace(0.0, 1.0, n)
    h = u * u * (3.0 - 2.0 * u)
    return np.column_stack([x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * h])


def turn_path(
    p0: np.ndarray, h0: np.ndarray, p3: np.ndarray, h3: np.ndarray, n: int = 16
) -> np.ndarray:
    """Cubic Bézier from p0 (heading h0) to p3 (heading h3), sampled at n points.

    Tangent handles are 0.4 × chord, which gives near-circular quarter turns. Collinear
    through movements degenerate to a straight line.
    """
    chord = float(np.sqrt(((p3 - p0) ** 2).sum()))
    k = 0.4 * chord
    c1 = p0 + h0 / np.sqrt((h0**2).sum()) * k
    c2 = p3 - h3 / np.sqrt((h3**2).sum()) * k
    t = np.linspace(0.0, 1.0, n)[:, None]
    omt = 1.0 - t
    return omt**3 * p0 + 3 * omt**2 * t * c1 + 3 * omt * t**2 * c2 + t**3 * p3


def end_heading(p: np.ndarray) -> np.ndarray:
    d = p[-1] - p[-2]
    return d / np.sqrt((d**2).sum())


def start_heading(p: np.ndarray) -> np.ndarray:
    d = p[1] - p[0]
    return d / np.sqrt((d**2).sum())


def point_to_polyline_xy(pt: np.ndarray, p: np.ndarray) -> float:
    """Shortest xy distance from a point to a polyline."""
    a, b = p[:-1, :2], p[1:, :2]
    ab = b - a
    t = ((pt[:2] - a) * ab).sum(axis=1) / (ab**2).sum(axis=1)
    t = np.clip(t, 0.0, 1.0)
    proj = a + ab * t[:, None]
    return float(np.sqrt(((proj - pt[:2]) ** 2).sum(axis=1)).min())
