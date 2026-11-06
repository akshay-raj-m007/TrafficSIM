"""Network -> JSON-ready dict (coordinates rounded to millimetres)."""

from __future__ import annotations

from typing import Any

import numpy as np

from trafficsim.network.types import Network


def _pts(a: np.ndarray) -> list[list[float]]:
    return np.round(a, 3).tolist()


def network_to_dict(net: Network) -> dict[str, Any]:
    return {
        "meta": {
            "units": "m",
            "axes": "x east, y north, z up",
            "drive_side": net.drive_side,
            **net.meta,
        },
        "roads": [
            {
                "id": r.id,
                "kind": r.kind,
                "level": r.level,
                "speed_limit_mps": round(r.speed_limit_mps, 4),
                "reference": _pts(r.reference),
                "inner_offset_m": r.inner_offset_m,
                "lanes": [
                    {
                        "id": ln.id,
                        "index": ln.index,
                        "width_m": ln.width_m,
                        "length_m": round(ln.length_m, 3),
                        "centreline": _pts(ln.centreline),
                    }
                    for ln in r.lanes
                ],
            }
            for r in net.roads
        ],
        "connectors": [
            {
                "id": c.id,
                "from_lane": c.from_lane,
                "to_lane": c.to_lane,
                "movement": c.movement,
                "junction_id": c.junction_id,
                "yields": c.yields,
                "length_m": round(c.length_m, 3),
                "path": _pts(c.path),
            }
            for c in net.connectors
        ],
        "junctions": [
            {
                "id": j.id,
                "control": j.control,
                "polygon": _pts(j.polygon),
                "approach_lanes": list(j.approach_lanes),
                "minor_approach_lanes": list(j.minor_approach_lanes),
            }
            for j in net.junctions
        ],
        "zones": [
            {"id": z.id, "entry_road": z.entry_road, "exit_road": z.exit_road} for z in net.zones
        ],
        "annotations": [
            {"text": a.text, "position": list(a.position), "kind": a.kind} for a in net.annotations
        ],
    }
