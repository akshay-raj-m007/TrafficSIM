/**
 * Decoder for the binary vehicle frames, format v2 (see backend/trafficsim/server/frames.py).
 *
 *   header, 12 bytes:  u8 type=2 | u8 J1 phase | u8 J1 state | u8 epoch | u32 tick |
 *                      u16 count n | u8 speed index | u8 pad
 *   body, 9 n bytes:   u16 id[n] | u16 segment[n] | u16 s[n] | i8 lateral[n] |
 *                      u8 speed[n] | u8 flags[n]                  (little-endian)
 *
 * A vehicle is given as (segment, arc length of its centre, lateral offset); `placeFrame`
 * puts it on the lane geometry with a `LanePlacer`, filling the world pose (x, y, z,
 * heading, pitch; simulation axes: x east, y north, z up, metres).
 */
import type { LanePlacer, Pose } from '../scene/laneGeometry';
import type { FrameFormat } from './types';

export const FRAME_TYPE = 2;
export const NO_SIGNAL = 255;

export interface Frame {
  tick: number;
  epoch: number;
  phase: number; // J1 phase index, or NO_SIGNAL
  state: number; // 0 green, 1 amber, 2 all-red, or NO_SIGNAL
  speedIndex: number;
  n: number;
  id: Uint16Array;
  seg: Uint16Array; // index into hello.segments
  s: Float32Array; // arc length of the vehicle centre on seg [m]
  lat: Float32Array; // lateral offset to the left of the lane [m] (lane-change blend)
  x: Float32Array;
  y: Float32Array;
  z: Float32Array;
  heading: Float32Array; // rad, CCW from east
  pitch: Float32Array; // rad, positive = nose up
  speed: Float32Array; // m/s
  brake: Uint8Array; // 0 / 1
  cls: Uint8Array; // vehicle class index
}

export function decodeFrame(buf: ArrayBuffer, fmt: FrameFormat): Frame {
  const view = new DataView(buf);
  if (buf.byteLength < fmt.header_bytes || view.getUint8(0) !== FRAME_TYPE) {
    throw new Error('not a vehicle frame');
  }
  const n = view.getUint16(8, true);
  if (buf.byteLength !== fmt.header_bytes + fmt.bytes_per_vehicle * n) {
    throw new Error(`frame size ${buf.byteLength} does not match ${n} vehicles`);
  }
  let off = fmt.header_bytes;
  const u16 = (): Uint16Array => {
    const a = new Uint16Array(buf, off, n);
    off += 2 * n;
    return a;
  };
  const id = u16();
  const seg = u16();
  const sq = u16();
  const latQ = new Int8Array(buf, off, n);
  off += n;
  const speedQ = new Uint8Array(buf, off, n);
  off += n;
  const flags = new Uint8Array(buf, off, n);

  const f32 = () => new Float32Array(n);
  const s = f32();
  const lat = f32();
  const x = f32();
  const y = f32();
  const z = f32();
  const heading = f32();
  const pitch = f32();
  const speed = f32();
  const brake = new Uint8Array(n);
  const cls = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    s[i] = sq[i]! * fmt.s_scale_m;
    lat[i] = latQ[i]! * fmt.lat_scale_m;
    speed[i] = speedQ[i]! * fmt.speed_scale_mps;
    brake[i] = flags[i]! & 1;
    cls[i] = flags[i]! >> 1;
  }
  return {
    tick: view.getUint32(4, true),
    epoch: view.getUint8(3),
    phase: view.getUint8(1),
    state: view.getUint8(2),
    speedIndex: view.getUint8(10),
    n,
    id: id.slice(),
    seg: seg.slice(),
    s,
    lat,
    x,
    y,
    z,
    heading,
    pitch,
    speed,
    brake,
    cls,
  };
}

/** Fill the world pose of every vehicle by placing it on the lane geometry (in place). */
export function placeFrame(f: Frame, placer: LanePlacer): Frame {
  const pose: Pose = { x: 0, y: 0, z: 0, heading: 0, pitch: 0 };
  for (let i = 0; i < f.n; i++) {
    placer.place(f.seg[i]!, f.s[i]!, f.lat[i]!, pose);
    f.x[i] = pose.x;
    f.y[i] = pose.y;
    f.z[i] = pose.z;
    f.heading[i] = pose.heading;
    f.pitch[i] = pose.pitch;
  }
  return f;
}
