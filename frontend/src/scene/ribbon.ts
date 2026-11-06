/**
 * Polyline geometry in SIMULATION coordinates (x east, y north, z up), metres.
 *
 * Lane surfaces are ribbons whose edges are the centreline offset by exactly ±width/2
 * using miter joins (same algorithm as backend/trafficsim/network/geometry.py), so every
 * edge segment is parallel to its centre segment at exactly half the lane width.
 * No scale factor is applied anywhere: 1 unit = 1 metre.
 */
import { writeSimPoint, type Vec3 } from './coords';

export function leftMiterNormals(pts: readonly Vec3[]): [number, number][] {
  const n = pts.length;
  if (n < 2) throw new Error('polyline needs at least 2 points');
  const seg: [number, number][] = [];
  for (let i = 0; i < n - 1; i++) {
    const dx = pts[i + 1]![0] - pts[i]![0];
    const dy = pts[i + 1]![1] - pts[i]![1];
    const len = Math.hypot(dx, dy);
    if (len <= 0) throw new Error('zero-length xy segment');
    seg.push([-dy / len, dx / len]); // rotate +90°: left of travel
  }
  const out: [number, number][] = [seg[0]!];
  for (let i = 1; i < n - 1; i++) {
    const a = seg[i - 1]!;
    const b = seg[i]!;
    const mx = a[0] + b[0];
    const my = a[1] + b[1];
    const ml = Math.hypot(mx, my);
    const ux = mx / ml;
    const uy = my / ml;
    const cosHalf = ux * b[0] + uy * b[1];
    out.push([ux / cosHalf, uy / cosHalf]);
  }
  out.push(seg[n - 2]!);
  return out;
}

export function offsetLeft(pts: readonly Vec3[], d: number): Vec3[] {
  const nrm = leftMiterNormals(pts);
  return pts.map((p, i) => [p[0] + nrm[i]![0] * d, p[1] + nrm[i]![1] * d, p[2]]);
}

export interface RibbonEdges {
  left: Vec3[];
  right: Vec3[];
}

export function ribbonEdges(centre: readonly Vec3[], width: number): RibbonEdges {
  return { left: offsetLeft(centre, width / 2), right: offsetLeft(centre, -width / 2) };
}

export interface MeshArrays {
  positions: Float32Array; // Three.js axes
  indices: Uint32Array;
}

/** Triangle strip between two edge polylines (same vertex count), lifted by `lift` m. */
export function stripArrays(left: readonly Vec3[], right: readonly Vec3[], lift = 0): MeshArrays {
  const n = left.length;
  const positions = new Float32Array(n * 2 * 3);
  for (let i = 0; i < n; i++) {
    writeSimPoint(positions, 2 * i, left[i]!, lift);
    writeSimPoint(positions, 2 * i + 1, right[i]!, lift);
  }
  const indices = new Uint32Array((n - 1) * 6);
  for (let i = 0; i < n - 1; i++) {
    const a = 2 * i;
    // Counter-clockwise seen from above (+y in Three.js) so faces point up.
    indices.set([a, a + 1, a + 2, a + 1, a + 3, a + 2], i * 6);
  }
  return { positions, indices };
}

export function ribbonArrays(centre: readonly Vec3[], width: number, lift = 0): MeshArrays {
  const { left, right } = ribbonEdges(centre, width);
  return stripArrays(left, right, lift);
}

export function polylineLength(pts: readonly Vec3[]): number {
  let s = 0;
  for (let i = 1; i < pts.length; i++) {
    s += Math.hypot(
      pts[i]![0] - pts[i - 1]![0],
      pts[i]![1] - pts[i - 1]![1],
      pts[i]![2] - pts[i - 1]![2],
    );
  }
  return s;
}

/** Point at arc length s along a polyline (clamped to its ends). */
export function pointAt(pts: readonly Vec3[], s: number): Vec3 {
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]!;
    const b = pts[i]!;
    const len = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    if (acc + len >= s && len > 0) {
      const t = Math.max(0, (s - acc) / len);
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    }
    acc += len;
  }
  return [...pts[pts.length - 1]!];
}

/** Sub-polylines of length `dash` separated by `gap`, following the source exactly. */
export function dashes(pts: readonly Vec3[], dash: number, gap: number): Vec3[][] {
  const total = polylineLength(pts);
  const out: Vec3[][] = [];
  for (let s = 0; s < total; s += dash + gap) {
    const e = Math.min(total, s + dash);
    if (e - s > 1e-6) out.push(subPolyline(pts, s, e));
  }
  return out;
}

export function subPolyline(pts: readonly Vec3[], s0: number, s1: number): Vec3[] {
  const out: Vec3[] = [pointAt(pts, s0)];
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]!;
    const b = pts[i]!;
    acc += Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    if (acc > s0 && acc < s1) out.push([...b]);
  }
  out.push(pointAt(pts, s1));
  return out;
}
