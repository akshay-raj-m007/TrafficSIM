/**
 * The ONLY place where simulation coordinates become Three.js coordinates.
 *
 * Simulation: x east, y north, z up (metres, right-handed).
 * Three.js:   x right, y up, z toward the viewer (right-handed).
 *
 * three = (sim.x, sim.z, -sim.y). This is a proper rotation (determinant +1) with
 * scale exactly 1: lengths, widths and handedness (left-hand traffic) are preserved.
 */
export type Vec3 = [number, number, number];

export function simToThree(p: readonly number[]): Vec3 {
  return [p[0]!, p[2]!, -p[1]!];
}

export function threeToSim(p: readonly number[]): Vec3 {
  return [p[0]!, -p[2]!, p[1]!];
}

/** Write a sim point into a flat Float32 position buffer in Three.js axes. */
export function writeSimPoint(buf: Float32Array, i: number, p: readonly number[], lift = 0): void {
  buf[i * 3] = p[0]!;
  buf[i * 3 + 1] = p[2]! + lift;
  buf[i * 3 + 2] = -p[1]!;
}
