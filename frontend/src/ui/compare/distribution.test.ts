import { describe, expect, it } from 'vitest';
import type { Distribution } from '../../api/compareTypes';
import { binShares, maxShare } from './distribution';

const dist = (counts: number[], overflow: number): Distribution => ({
  n: counts.reduce((s, c) => s + c, 0) + overflow,
  bin_s: 10,
  counts,
  overflow,
  box: null,
});

describe('binShares', () => {
  it('gives percentages of all completed trips, overflow included, summing to 100', () => {
    const s = binShares(dist([2, 6, 0, 1], 1));
    expect(s.bins).toEqual([20, 60, 0, 10]);
    expect(s.overflow).toBe(10);
    expect(s.bins.reduce((a, b) => a + b, 0) + s.overflow).toBeCloseTo(100);
  });
  it('handles a side without completed trips', () => {
    expect(binShares(dist([0, 0], 0))).toEqual({ bins: [0, 0], overflow: 0 });
  });
  it('uses one y range for both sides', () => {
    expect(maxShare(dist([1, 1], 0), dist([3, 1], 0))).toBe(75);
  });
});
