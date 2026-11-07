"""Compact binary vehicle frames for the renderer (little-endian, struct-of-arrays), v2.

    header, 12 bytes:  u8 type=2 | u8 J1 phase | u8 J1 state | u8 epoch | u32 tick |
                       u16 vehicle count n | u8 speed index | u8 pad
    body,  9 n bytes:  u16 id[n] | u16 segment[n] | u16 s[n] | i8 lateral[n] |
                       u8 speed[n] | u8 flags[n]

A vehicle is placed by *where it is on the lane graph*, not by world coordinates: its
segment (index into ``hello.segments``), the arc length ``s`` of its centre along that
segment, and a lateral offset (the visual lane-change blend). The browser puts it on the
real lane / turn-path geometry, so turns and ramps follow the curve at any playback speed.
A vehicle whose centre is still on the previous segment is sent on that (tail) segment.
Struct-of-arrays so columns are typed-array views and deflate sees similar bytes together.

Lane changes are instantaneous in the model; so a lane change does not look like a
teleport, the encoder blends a lateral offset over LC_BLEND_S (render-only state; the
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

FRAME_TYPE = 2
HEADER = struct.Struct("<BBBBIHBx")
BYTES_PER_VEHICLE = 9
NO_SIGNAL = 255
SIGNAL_STATE_CODE = {"green": 0, "amber": 1, "all_red": 2}

# Quantisation steps (see FrameFormat). Arc length 1 cm: a u16 spans 655 m, longer than any
# segment (checked in format_for). Lateral 5 cm in an i8: +-6.35 m, more than a lane width.
S_SCALE_M = 0.01
LAT_SCALE_M = 0.05
SPEED_SCALE_MPS = 0.1  # u8: 0 ... 25.5 m/s

# Brake-light convention (visual only): lit while decelerating at least this hard, or
# while standing still and not pulling away [m/s², m/s, m/s²].
BRAKE_LIGHT_DECEL_MPS2 = 0.5
STANDING_SPEED_MPS = 0.1
STANDING_ACC_MAX_MPS2 = 0.1
LC_BLEND_S = LC_COOLDOWN_S


@dataclass(frozen=True)
class FrameFormat:
    s_scale_m: float = S_SCALE_M
    lat_scale_m: float = LAT_SCALE_M
    speed_scale_mps: float = SPEED_SCALE_MPS
    header_bytes: int = HEADER.size
    bytes_per_vehicle: int = BYTES_PER_VEHICLE

    def to_dict(self) -> dict:
        return asdict(self)


def format_for(lg) -> FrameFormat:
    if float(lg.length.max()) / S_SCALE_M >= 65535:
        raise ValueError("a segment is too long for 16-bit arc lengths")
    return FrameFormat()


def segment_table(lg) -> list[dict]:
    """Segment list for ``hello``: index = position, so the frame needs no ids."""
    return [
        {"id": lg.ids[k], "length_m": float(lg.length[k]), "next": [int(b) for b in lg.succ[k]]}
        for k in range(lg.n)
    ]


def pack_frame(
    fmt: FrameFormat, *, phase: int, state: int, epoch: int, tick: int, speed_index: int,
    vid, seg, s, lat, speed, brake, cls,
) -> bytes:  # fmt: skip
    n = len(vid)
    head = HEADER.pack(FRAME_TYPE, phase, state, epoch & 255, tick, n, speed_index)
    flags = (np.asarray(brake, dtype=np.uint8) | (np.asarray(cls, dtype=np.uint8) << 1)).astype(
        "u1"
    )
    cols = [
        (np.asarray(vid, dtype=np.int64) & 0xFFFF).astype("<u2"),
        np.asarray(seg, dtype="<u2"),
        np.clip(np.rint(np.asarray(s) / fmt.s_scale_m), 0, 65535).astype("<u2"),
        np.clip(np.rint(np.asarray(lat) / fmt.lat_scale_m), -127, 127).astype("i1"),
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
    for name, dt in (("id", "<u2"), ("seg", "<u2"), ("s", "<u2"), ("lat", "i1"), ("v", "u1"),
                     ("f", "u1")):  # fmt: skip
        a = np.frombuffer(data, dtype=dt, count=n, offset=off)
        off += a.nbytes
        cols[name] = a
    return {
        "phase": phase, "state": state, "epoch": epoch, "tick": tick, "n": n,
        "speed_index": speed_index, "id": cols["id"].astype(int), "seg": cols["seg"].astype(int),
        "s": cols["s"] * fmt.s_scale_m, "lat": cols["lat"] * fmt.lat_scale_m,
        "speed": cols["v"] * fmt.speed_scale_mps,
        "brake": (cols["f"] & 1).astype(bool), "cls": (cols["f"] >> 1).astype(int),
    }  # fmt: skip


def world_pose(pose: PoseTable, d: dict):
    """x, y, z, heading, pitch of a decoded frame's vehicles (what the browser computes)."""
    x, y, z, h, p = pose.at(d["seg"], d["s"])
    return x - d["lat"] * np.sin(h), y + d["lat"] * np.cos(h), z, h, p


def _smoothstep(p: float) -> float:
    return p * p * (3.0 - 2.0 * p)


class FrameEncoder:
    """Turns the current simulation state into a binary frame (one per simulation)."""

    def __init__(self, sim) -> None:
        self.sim = sim
        self.pose = PoseTable(sim.network, sim.lg)
        self.fmt = format_for(sim.lg)
        self._lc_ptr = 0
        self._blend: dict[int, tuple[float, float]] = {}

    def _register_lane_changes(self) -> None:
        events = self.sim.log.lane_changes
        for e in events[self._lc_ptr :]:
            rows = np.flatnonzero(self.sim.vehicles.vid == e.vid)
            if not rows.size:
                continue
            half = LEN[self.sim.vehicles.cls[rows[0]]] / 2.0
            seg = np.array([e.from_seg, e.to_seg])
            x, y, _, h, _ = self.pose.at(seg, np.array([e.s_from - half, e.s_to - half]))
            dx, dy = x[0] - x[1], y[0] - y[1]  # old minus new lane position, as a left offset
            self._blend[e.vid] = (e.t, float(-dx * np.sin(h[1]) + dy * np.cos(h[1])))
        self._lc_ptr = len(events)

    def _apply_blends(self, lat) -> None:
        vs, t = self.sim.vehicles, self.sim.time_s
        for vid in list(self._blend):
            t0, offset = self._blend[vid]
            p = (t - t0) / LC_BLEND_S
            rows = np.flatnonzero(vs.vid == vid)
            if p >= 1.0 or not rows.size:
                del self._blend[vid]
                continue
            lat[rows[0]] += offset * (1.0 - _smoothstep(max(p, 0.0)))

    def encode(self, epoch: int, speed_index: int) -> bytes:
        sim = self.sim
        vs = sim.vehicles
        seg, s = self.pose.centre_of(vs)
        lat = np.zeros(len(vs.vid))
        self._register_lane_changes()
        self._apply_blends(lat)
        brake = (vs.acc <= -BRAKE_LIGHT_DECEL_MPS2) | (
            (vs.v < STANDING_SPEED_MPS) & (vs.acc < STANDING_ACC_MAX_MPS2)
        )
        ctrl = sim.signals[0] if sim.signals else None
        phase = ctrl.phase if ctrl else NO_SIGNAL
        state = SIGNAL_STATE_CODE[ctrl.state] if ctrl else NO_SIGNAL
        return pack_frame(
            self.fmt, phase=phase, state=state, epoch=epoch, tick=sim.tick,
            speed_index=speed_index, vid=vs.vid, seg=seg, s=s, lat=lat, speed=vs.v,
            brake=brake, cls=vs.cls,
        )  # fmt: skip
