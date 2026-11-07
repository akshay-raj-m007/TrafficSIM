import { describe, expect, it } from 'vitest';
import type { MetricRow } from '../../api/compareTypes';
import {
  droppedRuns,
  duration,
  formatInterval,
  formatValue,
  verdictOf,
  verdictText,
} from './tableFormat';

const row = (o: Partial<MetricRow>): MetricRow => ({
  id: 'x',
  label: 'X',
  unit: 's',
  n: 3,
  mean_a: 10,
  mean_b: 12,
  diff: 2,
  ci_lo: -0.5,
  ci_hi: 4.5,
  df: 2,
  t_crit: 4.3,
  p: 0.07,
  significant: false,
  identical: false,
  per_seed: [],
  ...o,
});

describe('numbers', () => {
  it('uses unit-appropriate decimals and explicit signs for differences', () => {
    expect(formatValue(12.345, 's')).toBe('12.3');
    expect(formatValue(3640.4, 'veh/h')).toBe('3640');
    expect(formatValue(0.5, 'ratio')).toBe('0.500');
    expect(formatValue(2, 's', true)).toBe('+2.0');
    expect(formatValue(-2, 's', true)).toBe('-2.0');
    expect(formatValue(null, 's')).toBe('—');
  });
  it('writes the interval with signs', () => {
    expect(formatInterval(row({}))).toBe('[-0.5, +4.5]');
    expect(formatInterval(row({ ci_lo: null, ci_hi: null }))).toBe('—');
  });
});

describe('the verdict is never hidden', () => {
  it('says plainly when the interval crosses zero, with the number of runs', () => {
    expect(verdictOf(row({}))).toBe('not-significant');
    expect(verdictText(row({}), 3)).toBe('NOT significant with 3 runs: the interval includes 0');
  });
  it('says which way a significant difference goes', () => {
    const r = row({ significant: true, ci_lo: 1, ci_hi: 3 });
    expect(verdictText(r, 5)).toContain('B higher');
    expect(verdictText(row({ significant: true, diff: -2, ci_lo: -3, ci_hi: -1 }), 5)).toContain(
      'B lower',
    );
  });
  it('handles identical runs, a single usable pair and undefined metrics', () => {
    expect(verdictText(row({ identical: true, significant: false, diff: 0 }), 3)).toContain(
      'identical',
    );
    expect(verdictText(row({ n: 1, significant: null, ci_lo: null, ci_hi: null }), 3)).toContain(
      'too few',
    );
    expect(verdictText(row({ n: 0, significant: null }), 3)).toContain('undefined');
    expect(droppedRuns(row({ n: 7 }), 10)).toBe(3);
  });
});

describe('durations', () => {
  it('reads naturally', () => {
    expect(duration(900)).toBe('15 min');
    expect(duration(90)).toBe('1 min 30 s');
    expect(duration(45)).toBe('45 s');
  });
});
