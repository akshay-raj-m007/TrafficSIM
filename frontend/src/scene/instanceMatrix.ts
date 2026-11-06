/**
 * Instance transforms for vehicle boxes, written straight into a column-major Float32Array.
 *
 * A vehicle has forward f, left l and up u in SIMULATION axes (x east, y north, z up):
 *   f = (cos h cos p, sin h cos p, sin p)      h = heading (CCW from east), p = pitch
 *   l = (-sin h,      cos h,       0)
 *   u = (-cos h sin p, -sin h sin p, cos p)    (f × l = u)
 * Three.js boxes are built with x = length (forward), y = height (up), z = width, and
 * z = f × u = −l (to the vehicle's right). The only axis conversion is coords.ts:
 * three = (x, z, −y), which is a proper rotation, so (f, u, −l) stays right-handed.
 * The pose from the server is the centre of the vehicle's footprint ON the road surface,
 * so the box centre sits half a height above it along u. Lengths are true metres.
 */

export interface Basis {
  fx: number;
  fy: number;
  fz: number; // forward, three axes
  ux: number;
  uy: number;
  uz: number; // up
  rx: number;
  ry: number;
  rz: number; // right (= −left)
}

export function basisOf(heading: number, pitch: number): Basis {
  const ch = Math.cos(heading);
  const sh = Math.sin(heading);
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  // sim → three: (x, y, z) → (x, z, −y)
  return {
    fx: ch * cp,
    fy: sp,
    fz: -(sh * cp),
    ux: -ch * sp,
    uy: cp,
    uz: sh * sp,
    rx: sh, // −l = (sin h, −cos h, 0) in sim → (sin h, 0, cos h) in three
    ry: 0,
    rz: ch,
  };
}

/**
 * Write a box instance: scale (sx, sy, sz) along (forward, up, right), centred
 * `up_offset` metres above the surface point (x, y, z) along the vehicle's up axis and
 * `fwd_offset` metres along its forward axis.
 */
export function writeBoxMatrix(
  out: Float32Array,
  k: number,
  pos: { x: number; y: number; z: number },
  heading: number,
  pitch: number,
  size: { sx: number; sy: number; sz: number },
  offset: { up: number; fwd: number } = { up: 0, fwd: 0 },
): void {
  const b = basisOf(heading, pitch);
  const o = k * 16;
  out[o] = b.fx * size.sx;
  out[o + 1] = b.fy * size.sx;
  out[o + 2] = b.fz * size.sx;
  out[o + 3] = 0;
  out[o + 4] = b.ux * size.sy;
  out[o + 5] = b.uy * size.sy;
  out[o + 6] = b.uz * size.sy;
  out[o + 7] = 0;
  out[o + 8] = b.rx * size.sz;
  out[o + 9] = b.ry * size.sz;
  out[o + 10] = b.rz * size.sz;
  out[o + 11] = 0;
  out[o + 12] = pos.x + b.ux * offset.up + b.fx * offset.fwd;
  out[o + 13] = pos.z + b.uy * offset.up + b.fy * offset.fwd;
  out[o + 14] = -pos.y + b.uz * offset.up + b.fz * offset.fwd;
  out[o + 15] = 1;
}
