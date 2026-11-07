/**
 * Places vehicles on the real lane and turn-path geometry (frame format v2).
 *
 * A frame gives each vehicle as (segment, arc length s of its centre, lateral offset). The
 * segment list in `hello` fixes the index -> id, length and successors; the polylines come
 * from the network JSON (`GET /api/network`), which the backend builds from the same
 * geometry the dynamics use. Between two frames a vehicle is moved along the successor
 * graph (lane -> junction connector -> lane), so a turn follows its curve at any playback
 * speed instead of cutting a chord.
 */
import type { NetworkData, SegmentInfo } from '../api/types';

/** Longest chain of segments searched between two consecutive frames: a frame spans at most
 *  ~17 m (10x) and the shortest segment is a truck long, so 5 is ample. */
export const MAX_PATH_SEGMENTS = 5;
/** Backwards motion within a segment tolerated as quantisation noise [m]. */
const BACKWARD_TOLERANCE_M = 0.02;
/** The network JSON rounds every coordinate to 1 mm: polyline length may drift per vertex. */
const LENGTH_TOLERANCE_PER_VERTEX_M = 1e-3;

export interface Pose {
  x: number;
  y: number;
  z: number;
  heading: number;
  pitch: number;
}

interface Polyline {
  x: Float64Array;
  y: Float64Array;
  z: Float64Array;
  cum: Float64Array; // arc length at each vertex
  heading: Float64Array; // per piece
  pitch: Float64Array; // per piece
}

function buildPolyline(points: readonly (readonly number[])[]): Polyline {
  const n = points.length;
  const p: Polyline = {
    x: new Float64Array(n),
    y: new Float64Array(n),
    z: new Float64Array(n),
    cum: new Float64Array(n),
    heading: new Float64Array(Math.max(n - 1, 1)),
    pitch: new Float64Array(Math.max(n - 1, 1)),
  };
  for (let i = 0; i < n; i++) {
    p.x[i] = points[i]![0]!;
    p.y[i] = points[i]![1]!;
    p.z[i] = points[i]![2]!;
    if (i === 0) continue;
    const dx = p.x[i]! - p.x[i - 1]!;
    const dy = p.y[i]! - p.y[i - 1]!;
    const dz = p.z[i]! - p.z[i - 1]!;
    p.cum[i] = p.cum[i - 1]! + Math.sqrt(dx * dx + dy * dy + dz * dz);
    p.heading[i - 1] = Math.atan2(dy, dx);
    p.pitch[i - 1] = Math.atan2(dz, Math.sqrt(dx * dx + dy * dy));
  }
  return p;
}

/** A placer for this network and segment table, or null if they do not belong together
 *  (the hello of a restarted session arrives before the matching network has been fetched). */
export function tryBuildPlacer(
  net: NetworkData,
  segments: readonly SegmentInfo[],
): LanePlacer | null {
  try {
    return new LanePlacer(net, segments);
  } catch {
    return null;
  }
}

export class LanePlacer {
  private readonly lines: Polyline[];
  private readonly pathCache = new Map<number, number[] | null>();

  constructor(
    net: NetworkData,
    readonly segments: readonly SegmentInfo[],
  ) {
    const byId = new Map<string, readonly (readonly number[])[]>();
    for (const r of net.roads) for (const l of r.lanes) byId.set(l.id, l.centreline);
    for (const c of net.connectors) byId.set(c.id, c.path);
    this.lines = segments.map((s) => {
      const pts = byId.get(s.id);
      if (!pts) throw new Error(`segment ${s.id} is not in the network geometry`);
      const line = buildPolyline(pts);
      const len = line.cum[line.cum.length - 1]!;
      if (Math.abs(len - s.length_m) > LENGTH_TOLERANCE_PER_VERTEX_M * pts.length) {
        throw new Error(`segment ${s.id}: polyline length ${len} differs from ${s.length_m}`);
      }
      return line;
    });
  }

  get count(): number {
    return this.segments.length;
  }

  /** Pose at arc length `s` (clamped) on segment `seg`, shifted `lat` m to its left. */
  place(seg: number, s: number, lat: number, out: Pose): Pose {
    const line = this.lines[seg]!;
    const cum = line.cum;
    const last = cum.length - 1;
    const q = Math.min(Math.max(s, 0), cum[last]!);
    let lo = 0;
    let hi = last;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (cum[mid]! <= q) lo = mid;
      else hi = mid;
    }
    const piece = Math.min(lo, last - 1);
    const den = cum[piece + 1]! - cum[piece]!;
    const t = den > 0 ? (q - cum[piece]!) / den : 0;
    const h = line.heading[piece]!;
    out.x = line.x[piece]! + t * (line.x[piece + 1]! - line.x[piece]!) - lat * Math.sin(h);
    out.y = line.y[piece]! + t * (line.y[piece + 1]! - line.y[piece]!) + lat * Math.cos(h);
    out.z = line.z[piece]! + t * (line.z[piece + 1]! - line.z[piece]!);
    out.heading = h;
    out.pitch = line.pitch[piece]!;
    return out;
  }

  /** Segments from `a` to `b` along the successor graph (inclusive), or null. */
  private path(a: number, b: number): number[] | null {
    const key = a * this.segments.length + b;
    const hit = this.pathCache.get(key);
    if (hit !== undefined) return hit;
    let found: number[] | null = null;
    let frontier: number[][] = [[a]];
    for (let depth = 1; depth <= MAX_PATH_SEGMENTS; depth++) {
      found = frontier.find((p) => p[p.length - 1] === b) ?? null;
      if (found || depth === MAX_PATH_SEGMENTS) break;
      frontier = frontier.flatMap((p) =>
        this.segments[p[p.length - 1]!]!.next.map((nx) => [...p, nx]),
      );
    }
    this.pathCache.set(key, found);
    return found;
  }

  /**
   * Pose a fraction `u` of the way from (a, sa) to (b, sb) *along the lanes*. Returns false
   * (and leaves `out` untouched) if b cannot be reached from a, e.g. a lane change: the
   * caller then interpolates the two world poses instead.
   */
  between(
    a: number,
    sa: number,
    b: number,
    sb: number,
    lat: number,
    u: number,
    out: Pose,
  ): boolean {
    if (a === b) {
      if (sb < sa - BACKWARD_TOLERANCE_M) return false;
      this.place(a, sa + (sb - sa) * u, lat, out);
      return true;
    }
    const p = this.path(a, b);
    if (!p) return false;
    const lengths = this.segments;
    let total = lengths[a]!.length_m - sa + sb;
    for (let i = 1; i < p.length - 1; i++) total += lengths[p[i]!]!.length_m;
    let d = u * total;
    let first = lengths[a]!.length_m - sa;
    if (d <= first) {
      this.place(a, sa + d, lat, out);
      return true;
    }
    d -= first;
    for (let i = 1; i < p.length - 1; i++) {
      first = lengths[p[i]!]!.length_m;
      if (d <= first) {
        this.place(p[i]!, d, lat, out);
        return true;
      }
      d -= first;
    }
    this.place(b, Math.min(d, sb), lat, out);
    return true;
  }
}
