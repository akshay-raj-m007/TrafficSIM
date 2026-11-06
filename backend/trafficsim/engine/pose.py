"""World pose of vehicles, evaluated on the real lane and turn-path geometry.

Every segment (lane or junction connector) is a 3-D polyline whose arc length equals the
segment length the dynamics use. The pose of a vehicle is that of its *centre*, i.e. the
point half a vehicle length behind the front bumper along its path; a vehicle whose
centre is still on the previous segment (its ``tail``) is placed there. Heading and
pitch are those of the polyline piece under the centre (pitch positive when climbing),
so ramps and the flyover deck carry their real elevation and slope.

All polylines are concatenated into one array with key = segment · KEY_STRIDE + arc
length, so a single ``searchsorted`` evaluates every vehicle at once.
"""

from __future__ import annotations

import numpy as np

from trafficsim.engine.lanegraph import LaneGraph
from trafficsim.engine.leaders import KEY_STRIDE
from trafficsim.engine.vehicle import LEN, VehicleState
from trafficsim.network.types import Network


class PoseTable:
    def __init__(self, net: Network, lg: LaneGraph) -> None:
        self.lg = lg
        paths = {c.id: c.path for c in net.connectors}
        keys, xyz, head, pitch = [], [], [], []
        for k, sid in enumerate(lg.ids):
            line = paths[sid] if lg.is_conn[k] else net.lane(sid).centreline
            d = np.diff(line, axis=0)
            ds = np.sqrt((d**2).sum(axis=1))
            cum = np.concatenate([[0.0], np.cumsum(ds)])
            if abs(cum[-1] - lg.length[k]) > 1e-6:
                raise ValueError(f"segment {sid}: polyline length differs from segment length")
            h = np.arctan2(d[:, 1], d[:, 0])
            p = np.arctan2(d[:, 2], np.sqrt(d[:, 0] ** 2 + d[:, 1] ** 2))
            keys.append(k * KEY_STRIDE + cum)
            xyz.append(line)
            head.append(np.concatenate([h, h[-1:]]))  # last vertex repeats the last piece
            pitch.append(np.concatenate([p, p[-1:]]))
        self.key = np.concatenate(keys)
        self.xyz = np.vstack(xyz)
        self.heading = np.concatenate(head)
        self.pitch = np.concatenate(pitch)

    def at(self, seg: np.ndarray, s: np.ndarray):
        """Pose at arc length ``s`` (clamped to the segment) on ``seg``: x, y, z, heading, pitch."""
        s = np.clip(s, 0.0, self.lg.length[seg])
        q = seg * KEY_STRIDE + s
        i = np.searchsorted(self.key, q, side="right") - 1
        j = np.minimum(i + 1, self.key.size - 1)
        den = self.key[j] - self.key[i]
        t = np.where(den > 0.0, (q - self.key[i]) / np.where(den > 0.0, den, 1.0), 0.0)
        p = self.xyz[i] + t[:, None] * (self.xyz[j] - self.xyz[i])
        return p[:, 0], p[:, 1], p[:, 2], self.heading[i], self.pitch[i]

    def centre_of(self, vs: VehicleState) -> tuple[np.ndarray, np.ndarray]:
        """(segment, arc length) of each vehicle's centre point."""
        s_c = vs.s - LEN[vs.cls] / 2.0
        seg = vs.seg.astype(np.int64).copy()
        s = s_c.copy()
        back = (s_c < 0.0) & (vs.tail >= 0)
        seg[back] = vs.tail[back]
        s[back] = self.lg.length[vs.tail[back]] + s_c[back]
        return seg, s

    def vehicle_poses(self, vs: VehicleState):
        seg, s = self.centre_of(vs)
        return self.at(seg, s)
