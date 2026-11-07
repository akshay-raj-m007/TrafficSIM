import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { NetworkData, SegmentInfo } from '../api/types';
import { shortestAngleDelta } from './interpolator';
import { LanePlacer, type Pose } from './laneGeometry';

/** Written by backend/tools/gen_golden_frame.py: the demo network, its lane-graph segment
 *  table and the server-side world pose (PoseTable) of 400 probe points. */
const fx = JSON.parse(
  readFileSync(new URL('../api/fixtures/placement.json', import.meta.url), 'utf-8'),
) as {
  network: NetworkData;
  segments: SegmentInfo[];
  probes: { seg: number; s: number; lat: number; pose: number[] }[];
};
const placer = new LanePlacer(fx.network, fx.segments);
// The network JSON is rounded to 1 mm, which moves the direction of a 0.5 m piece by ~2 mrad.
const HEADING_TOL_RAD = 5e-3;
const P = (): Pose => ({ x: 0, y: 0, z: 0, heading: 0, pitch: 0 });

describe('placement agrees with the server pose table', () => {
  it('matches 400 probe points on every kind of segment within 5 mm (the network JSON is rounded to 1 mm)', () => {
    let worst = 0;
    for (const p of fx.probes) {
      const o = placer.place(p.seg, p.s, p.lat, P());
      const [x, y, z, h, pit] = p.pose as [number, number, number, number, number];
      worst = Math.max(worst, Math.hypot(o.x - x, o.y - y), Math.abs(o.z - z));
      expect(Math.abs(shortestAngleDelta(h, o.heading))).toBeLessThan(HEADING_TOL_RAD);
      expect(Math.abs(o.pitch - pit)).toBeLessThan(HEADING_TOL_RAD);
    }
    console.log(`[placement] worst position difference to the server: ${(worst * 1000).toFixed(2)} mm`);
    expect(worst).toBeLessThan(0.005);
  });
});

describe('turns follow the connector curve at any speed', () => {
  const conn = fx.network.connectors.find((c) => c.junction_id === 'J1' && c.movement === 'left')!;
  const ci = fx.segments.findIndex((s) => s.id === conn.id);
  const from = fx.segments.findIndex((s) => s.id === conn.from_lane);
  const to = fx.segments.findIndex((s) => s.id === conn.to_lane);

  it('is reachable through the successor graph', () => {
    expect(fx.segments[from]!.next).toContain(ci);
    expect(fx.segments[ci]!.next).toContain(to);
  });

  it('a 10x frame pair spanning the whole turn stays on the path, a chord would not', () => {
    const lenFrom = fx.segments[from]!.length_m;
    const lenConn = fx.segments[ci]!.length_m;
    const sa = lenFrom - 4;
    const sb = 5;
    const curve = Array.from({ length: 6000 }, (_, k) =>
      placer.place(ci, (k / 5999) * lenConn, 0, P()),
    ).map((p) => [p.x, p.y] as const);
    const distToCurve = (x: number, y: number) =>
      Math.min(...curve.map(([cx, cy]) => Math.hypot(cx - x, cy - y)));
    const a = placer.place(from, sa, 0, P());
    const b = placer.place(to, sb, 0, P());
    const total = lenFrom - sa + lenConn + sb;
    let worstPath = 0;
    let worstChord = 0;
    let steps = 0;
    for (let u = 0.02; u <= 0.98; u += 0.02) {
      const o = P();
      expect(placer.between(from, sa, to, sb, 0, u, o)).toBe(true);
      const d = u * total;
      if (d > lenFrom - sa && d < lenFrom - sa + lenConn) {
        worstPath = Math.max(worstPath, distToCurve(o.x, o.y));
        const cx = a.x + (b.x - a.x) * u;
        const cy = a.y + (b.y - a.y) * u;
        worstChord = Math.max(worstChord, distToCurve(cx, cy));
        steps++;
      }
    }
    console.log(
      `[turn] ${conn.id}: ${steps} samples inside the connector; ` +
        `on-path error ${(worstPath * 100).toFixed(2)} cm, chord error ${worstChord.toFixed(2)} m`,
    );
    expect(steps).toBeGreaterThan(3);
    expect(worstPath).toBeLessThan(0.01); // within 1 cm of the connector polyline
    expect(worstChord).toBeGreaterThan(0.3); // the old chord cut the corner by this much
  });

  it('refuses unconnected positions (a lane change) so the caller blends world poses', () => {
    const road = fx.network.roads.find((r) => r.lanes.length >= 2)!;
    const a = fx.segments.findIndex((s) => s.id === road.lanes[0]!.id);
    const b = fx.segments.findIndex((s) => s.id === road.lanes[1]!.id);
    expect(placer.between(a, 10, b, 12, 0, 0.5, P())).toBe(false);
  });
});
