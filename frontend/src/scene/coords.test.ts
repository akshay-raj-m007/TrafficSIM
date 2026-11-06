import { describe, expect, it } from 'vitest';
import { simToThree, threeToSim, writeSimPoint } from './coords';

describe('sim → three axis mapping', () => {
  it('maps east→x, up→y, north→-z with scale exactly 1', () => {
    expect(simToThree([1, 0, 0])).toEqual([1, 0, -0]);
    expect(simToThree([0, 1, 0])).toEqual([0, 0, -1]);
    expect(simToThree([0, 0, 1])).toEqual([0, 1, -0]);
  });

  it('is a proper rotation (det +1): preserves handedness, so LHT stays LHT', () => {
    const ex = simToThree([1, 0, 0]);
    const ey = simToThree([0, 1, 0]);
    const ez = simToThree([0, 0, 1]);
    const det =
      ex[0] * (ey[1] * ez[2] - ey[2] * ez[1]) -
      ex[1] * (ey[0] * ez[2] - ey[2] * ez[0]) +
      ex[2] * (ey[0] * ez[1] - ey[1] * ez[0]);
    expect(det).toBe(1);
  });

  it('preserves distances', () => {
    const a = [12.5, -9.75, 6.5];
    const b = [-300, 13.25, 0];
    const d = Math.hypot(a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!);
    const ta = simToThree(a);
    const tb = simToThree(b);
    expect(Math.hypot(ta[0] - tb[0], ta[1] - tb[1], ta[2] - tb[2])).toBe(d);
  });

  it('round-trips', () => {
    expect(threeToSim(simToThree([3, 4, 5]))).toEqual([3, 4, 5]);
  });

  it('writes buffers in three axes with optional lift', () => {
    const buf = new Float32Array(3);
    writeSimPoint(buf, 0, [10, 20, 6.5], 0.02);
    expect(Array.from(buf)).toEqual([10, Math.fround(6.52), -20]);
  });
});
