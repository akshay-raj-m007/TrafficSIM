import { describe, expect, it } from 'vitest';
import { linear, niceTicks } from './plot';

describe('plot helpers', () => {
  it('gives round tick values inside the range', () => {
    expect(niceTicks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(3, 47, 4)).toEqual([20, 40]);
    expect(niceTicks(0, 1, 5)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
  });
  it('handles an empty range', () => {
    expect(niceTicks(5, 5)).toEqual([5]);
  });
  it('maps linearly, also onto a reversed range', () => {
    const f = linear(0, 10, 100, 0);
    expect(f(0)).toBe(100);
    expect(f(10)).toBe(0);
    expect(f(2.5)).toBe(75);
  });
});
