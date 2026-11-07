"""Exact fingerprint of a network: per-element hashes of every coordinate, id and attribute."""

import hashlib

import numpy as np


def _h(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(
            np.ascontiguousarray(p).tobytes() if isinstance(p, np.ndarray) else repr(p).encode()
        )
    return h.hexdigest()[:16]


def fingerprint(net) -> dict:
    roads = {
        r.id: _h(r.kind, r.level, r.speed_limit_mps, r.reference, r.inner_offset_m,
                 *[(ln.id, ln.index, ln.width_m, ln.length_m, ln.centreline) for ln in r.lanes])
        for r in net.roads
    }  # fmt: skip
    conns = {
        c.id: _h(c.from_lane, c.to_lane, c.movement, c.junction_id, c.yields, c.length_m, c.path)
        for c in net.connectors
    }
    juncs = {
        j.id: _h(j.control, j.polygon, j.connector_ids, j.approach_lanes, j.minor_approach_lanes)
        for j in net.junctions
    }
    return {
        "roads": roads, "connectors": conns, "junctions": juncs,
        "zones": [_h(z.id, z.entry_road, z.exit_road) for z in net.zones],
        "annotations": [
            _h(a.text, tuple(float(v) for v in a.position), a.kind) for a in net.annotations
        ],
        "meta": _h(sorted(net.meta.items()), net.drive_side),
    }  # fmt: skip
