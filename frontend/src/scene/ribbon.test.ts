import { describe, expect, it } from 'vitest';
import type { Vec3 } from './coords';
import { dashes, offsetLeft, polylineLength, ribbonArrays, ribbonEdges } from './ribbon';

/** Shortest xy distance from a point to a polyline. */
function distToPolyline(p: Vec3, line: Vec3[]): number {
  let best = Infinity;
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1]!;
    const b = line[i]!;
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    let t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / (abx * abx + aby * aby);
    t = Math.min(1, Math.max(0, t));
    best = Math.min(best, Math.hypot(a[0] + abx * t - p[0], a[1] + aby * t - p[1]));
  }
  return best;
}

const straight: Vec3[] = [
  [-450, 0, 0],
  [-15, 0, 0],
];
const arc: Vec3[] = Array.from({ length: 40 }, (_, i) => {
  const th = (1.5 * i) / 39;
  return [50 * Math.cos(th), 50 * Math.sin(th), 0] as Vec3;
});

describe('ribbon width is exactly the lane width (1 unit = 1 m)', () => {
  for (const [name, line] of [
    ['straight', straight],
    ['curved', arc],
  ] as const) {
    for (const width of [2.75, 3.0, 3.25, 3.5]) {
      it(`${name} centreline, width ${width} m`, () => {
        const { left, right } = ribbonEdges(line, width);
        for (const p of left) expect(distToPolyline(p, right)).toBeCloseTo(width, 9);
        for (const p of left.slice(1, -1)) expect(distToPolyline(p, line)).toBeCloseTo(width / 2, 9);
      });
    }
  }

  it('left edge is on the left of travel (north for an eastbound lane)', () => {
    const { left, right } = ribbonEdges(straight, 3.5);
    expect(left[0]![1]).toBeCloseTo(1.75, 12);
    expect(right[0]![1]).toBeCloseTo(-1.75, 12);
  });

  it('offset composes: offsetting by a then b equals offsetting by a+b', () => {
    const twice = offsetLeft(offsetLeft(arc, 3.5), 3.5);
    const once = offsetLeft(arc, 7);
    twice.forEach((p, i) => {
      expect(p[0]).toBeCloseTo(once[i]![0], 6);
      expect(p[1]).toBeCloseTo(once[i]![1], 6);
    });
  });

  it('float32 mesh buffer keeps the width to well under a millimetre', () => {
    const { positions } = ribbonArrays(straight, 3.5);
    // vertices 0 and 1 are the left/right edge at the first centreline point
    const dz = positions[2]! - positions[5]!; // three z = -sim y
    expect(Math.abs(dz)).toBeCloseTo(3.5, 4);
  });

  it('elevation follows the centreline (ramps are not flattened)', () => {
    const ramp: Vec3[] = [
      [0, 0, 0],
      [90, 0, 3.25],
      [180, 0, 6.5],
    ];
    const { positions } = ribbonArrays(ramp, 3.5);
    expect(positions[1]).toBe(0);
    expect(positions[3 * 5 + 1]).toBeCloseTo(6.5, 6);
  });
});

describe('dashes', () => {
  it('cover the line with dash/gap rhythm and stay on it', () => {
    const d = dashes(straight, 3, 4.5);
    expect(d.length).toBe(Math.ceil(435 / 7.5));
    for (const seg of d) {
      expect(polylineLength(seg)).toBeLessThanOrEqual(3 + 1e-9);
      for (const p of seg) expect(p[1]).toBe(0);
    }
  });
});
