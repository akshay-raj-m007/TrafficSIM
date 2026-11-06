/**
 * Decoder for the binary vehicle frames (see backend/trafficsim/server/frames.py).
 *
 *   header, 12 bytes:  u8 type=1 | u8 J1 phase | u8 J1 state | u8 epoch | u32 tick |
 *                      u16 count n | u8 speed index | u8 pad
 *   body, 13 n bytes:  u16 id[n] | u16 x[n] | u16 y[n] | u16 z[n] | u16 heading[n] |
 *                      i8 pitch[n] | u8 speed[n] | u8 flags[n]       (little-endian)
 *
 * Columns are viewed as typed arrays directly over the received buffer; physical units
 * are recovered with the quantisation steps from `hello`. Positions are in SIMULATION
 * axes (x east, y north, z up), in metres.
 */
import type { FrameFormat } from './types';

export const FRAME_TYPE = 1;
export const NO_SIGNAL = 255;

export interface Frame {
  tick: number;
  epoch: number;
  phase: number; // J1 phase index, or NO_SIGNAL
  state: number; // 0 green, 1 amber, 2 all-red, or NO_SIGNAL
  speedIndex: number;
  n: number;
  id: Uint16Array;
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
  const xq = u16();
  const yq = u16();
  const zq = u16();
  const hq = u16();
  const pitchQ = new Int8Array(buf, off, n);
  off += n;
  const speedQ = new Uint8Array(buf, off, n);
  off += n;
  const flags = new Uint8Array(buf, off, n);

  const x = new Float32Array(n);
  const y = new Float32Array(n);
  const z = new Float32Array(n);
  const heading = new Float32Array(n);
  const pitch = new Float32Array(n);
  const speed = new Float32Array(n);
  const brake = new Uint8Array(n);
  const cls = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = xq[i]! * fmt.pos_scale_m + fmt.x0_m;
    y[i] = yq[i]! * fmt.pos_scale_m + fmt.y0_m;
    z[i] = zq[i]! * fmt.z_scale_m + fmt.z0_m;
    heading[i] = hq[i]! * fmt.heading_scale_rad;
    pitch[i] = pitchQ[i]! * fmt.pitch_scale_rad;
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
