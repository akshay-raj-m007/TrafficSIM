"""Compact binary vehicle frames for the renderer (little-endian, struct-of-arrays).

    header, 12 bytes:  u8 type=1 | u8 J1 phase | u8 J1 state | u8 epoch | u32 tick |
                       u16 vehicle count n | u8 speed index | u8 pad
    body,  13 n bytes: u16 id[n] | u16 x[n] | u16 y[n] | u16 z[n] | u16 heading[n] |
                       i8 pitch[n] | u8 speed[n] | u8 flags[n]

Struct-of-arrays so the browser can view each column as a typed array directly and so
deflate (permessage-deflate on the WebSocket) sees similar bytes together. Only what the
renderer needs: id (low 16 bits of the vehicle id, unique among concurrently active
vehicles), pose of the vehicle's centre, speed (colour) and flags (brake light, class).
Quantisation steps are in ``FrameFormat`` and travel to the client in ``hello``.

Lane changes are instantaneous in the model; so a lane change does not look like a
teleport, the encoder blends the lateral offset over LC_BLEND_S (render-only state; the
engine is untouched). The blend never overlaps another because of the lane-change
cooldown of the same length.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

import numpy as np

from trafficsim.engine.params.driving import LC_COOLDOWN_S
from trafficsim.engine.pose import PoseTable
from trafficsim.engine.vehicle import LEN

FRAME_TYPE = 1
HEADER = struct.Struct("<BBBBIHBx")
BYTES_PER_VEHICLE = 13
NO_SIGNAL = 255
SIGNAL_STATE_CODE = {"green": 0, "amber": 1, "all_red": 2}

# Quantisation steps (see FrameFormat). Position 0.05 m: a u16 spans 3.3 km, enough for
# the 2.5 km demo network; error <= 2.5 cm, invisible next to 4.5 m cars.
POS_SCALE_M = 0.05
Z_SCALE_M = 0.01  # u16 from Z_ORIGIN_M: -1 m ... 654 m
Z_ORIGIN_M = -1.0
HEADING_SCALE_RAD = 2.0 * np.pi / 65536.0
PITCH_SCALE_RAD = 0.001  # i8: +-0.127 rad (the steepest ramp is 0.054)
SPEED_SCALE_MPS = 0.1  # u8: 0 ... 25.5 m/s
EXTENT_MARGIN_M = 5.0

# Brake-light convention (visual only): lit while decelerating at least this hard, or
# while standing still and not pulling away [m/s², m/s, m/s²].
BRAKE_LIGHT_DECEL_MPS2 = 0.5
STANDING_SPEED_MPS = 0.1
STANDING_ACC_MAX_MPS2 = 0.1
LC_BLEND_S = LC_COOLDOWN_S


@dataclass(frozen=True)
class FrameFormat:
    x0_m: float
    y0_m: float
    pos_scale_m: float = POS_SCALE_M
    z0_m: float = Z_ORIGIN_M
    z_scale_m: float = Z_SCALE_M
    heading_scale_rad: float = HEADING_SCALE_RAD
    pitch_scale_rad: float = PITCH_SCALE_RAD
    speed_scale_mps: float = SPEED_SCALE_MPS
    header_bytes: int = HEADER.size
    bytes_per_vehicle: int = BYTES_PER_VEHICLE

    def to_dict(self) -> dict:
        return asdict(self)


def format_for(net) -> FrameFormat:
    pts = np.vstack([ln.centreline for r in net.roads for ln in r.lanes])
    fmt = FrameFormat(
        float(pts[:, 0].min() - EXTENT_MARGIN_M), float(pts[:, 1].min() - EXTENT_MARGIN_M)
    )
    span = max(pts[:, 0].max() - fmt.x0_m, pts[:, 1].max() - fmt.y0_m) + EXTENT_MARGIN_M
    if span / POS_SCALE_M >= 65535:
        raise ValueError("network too large for 16-bit positions")
    return fmt


def _u16(a: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(a), 0, 65535).astype("<u2")


def pack_frame(
    fmt: FrameFormat, *, phase: int, state: int, epoch: int, tick: int, speed_index: int,
    vid, x, y, z, heading, pitch, speed, brake, cls,
) -> bytes:  # fmt: skip
    n = len(vid)
    head = HEADER.pack(FRAME_TYPE, phase, state, epoch & 255, tick, n, speed_index)
    flags = (np.asarray(brake, dtype=np.uint8) | (np.asarray(cls, dtype=np.uint8) << 1)).astype(
        "u1"
    )
    cols = [
        (np.asarray(vid, dtype=np.int64) & 0xFFFF).astype("<u2"),
        _u16((np.asarray(x) - fmt.x0_m) / fmt.pos_scale_m),
        _u16((np.asarray(y) - fmt.y0_m) / fmt.pos_scale_m),
        _u16((np.asarray(z) - fmt.z0_m) / fmt.z_scale_m),
        (np.rint(np.mod(np.asarray(heading), 2 * np.pi) / fmt.heading_scale_rad).astype(np.int64)
         & 0xFFFF).astype("<u2"),
        np.clip(np.rint(np.asarray(pitch) / fmt.pitch_scale_rad), -127, 127).astype("i1"),
        np.clip(np.rint(np.asarray(speed) / fmt.speed_scale_mps), 0, 255).astype("u1"),
        flags,
    ]  # fmt: skip
    return head + b"".join(c.tobytes() for c in cols)


def unpack_frame(fmt: FrameFormat, data: bytes) -> dict:
    """Decode a frame back to physical units (used by tests and tools)."""
    typ, phase, state, epoch, tick, n, speed_index = HEADER.unpack_from(data, 0)
    if typ != FRAME_TYPE or len(data) != HEADER.size + BYTES_PER_VEHICLE * n:
        raise ValueError("malformed frame")
    off = HEADER.size
    cols = {}
    for name, dt in (("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "<u2"), ("h", "<u2"),
                     ("p", "i1"), ("v", "u1"), ("f", "u1")):  # fmt: skip
        a = np.frombuffer(data, dtype=dt, count=n, offset=off)
        off += a.nbytes
        cols[name] = a
    return {
        "phase": phase, "state": state, "epoch": epoch, "tick": tick, "n": n,
        "speed_index": speed_index, "id": cols["id"].astype(int),
        "x": cols["x"] * fmt.pos_scale_m + fmt.x0_m, "y": cols["y"] * fmt.pos_scale_m + fmt.y0_m,
        "z": cols["z"] * fmt.z_scale_m + fmt.z0_m, "heading": cols["h"] * fmt.heading_scale_rad,
        "pitch": cols["p"] * fmt.pitch_scale_rad, "speed": cols["v"] * fmt.speed_scale_mps,
        "brake": (cols["f"] & 1).astype(bool), "cls": (cols["f"] >> 1).astype(int),
    }  # fmt: skip


def _smoothstep(p: float) -> float:
    return p * p * (3.0 - 2.0 * p)


class FrameEncoder:
    """Turns the current simulation state into a binary frame (one per simulation)."""

    def __init__(self, sim) -> None:
        self.sim = sim
        self.pose = PoseTable(sim.network, sim.lg)
        self.fmt = format_for(sim.network)
        self._lc_ptr = 0
        self._blend: dict[int, tuple[float, float, float, float]] = {}

    def _register_lane_changes(self) -> None:
        events = self.sim.log.lane_changes
        for e in events[self._lc_ptr :]:
            rows = np.flatnonzero(self.sim.vehicles.vid == e.vid)
            if not rows.size:
                continue
            half = LEN[self.sim.vehicles.cls[rows[0]]] / 2.0
            seg = np.array([e.from_seg, e.to_seg])
            x, y, z, _, _ = self.pose.at(seg, np.array([e.s_from - half, e.s_to - half]))
            self._blend[e.vid] = (e.t, x[0] - x[1], y[0] - y[1], z[0] - z[1])
        self._lc_ptr = len(events)

    def _apply_blends(self, x, y, z) -> None:
        vs, t = self.sim.vehicles, self.sim.time_s
        for vid in list(self._blend):
            t0, dx, dy, dz = self._blend[vid]
            p = (t - t0) / LC_BLEND_S
            rows = np.flatnonzero(vs.vid == vid)
            if p >= 1.0 or not rows.size:
                del self._blend[vid]
                continue
            w = 1.0 - _smoothstep(max(p, 0.0))
            x[rows[0]] += dx * w
            y[rows[0]] += dy * w
            z[rows[0]] += dz * w

    def encode(self, epoch: int, speed_index: int) -> bytes:
        sim = self.sim
        vs = sim.vehicles
        x, y, z, heading, pitch = (np.array(a) for a in self.pose.vehicle_poses(vs))
        self._register_lane_changes()
        self._apply_blends(x, y, z)
        brake = (vs.acc <= -BRAKE_LIGHT_DECEL_MPS2) | (
            (vs.v < STANDING_SPEED_MPS) & (vs.acc < STANDING_ACC_MAX_MPS2)
        )
        ctrl = sim.signals[0] if sim.signals else None
        phase = ctrl.phase if ctrl else NO_SIGNAL
        state = SIGNAL_STATE_CODE[ctrl.state] if ctrl else NO_SIGNAL
        return pack_frame(
            self.fmt, phase=phase, state=state, epoch=epoch, tick=sim.tick,
            speed_index=speed_index, vid=vs.vid, x=x, y=y, z=z, heading=heading, pitch=pitch,
            speed=vs.v, brake=brake, cls=vs.cls,
        )  # fmt: skip
