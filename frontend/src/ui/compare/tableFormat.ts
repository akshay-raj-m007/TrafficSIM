/** Presentation logic of the comparison table (pure): number formats and the verdict text. */
import type { MetricRow } from '../../api/compareTypes';

const DECIMALS: Record<string, number> = { s: 1, 'veh/h': 0, veh: 1, m: 1, ratio: 3 };

export function formatValue(v: number | null, unit: string, signed = false): string {
  if (v === null) return '—';
  const d = DECIMALS[unit] ?? 2;
  const s = v.toFixed(d);
  return signed && v > 0 ? `+${s}` : s;
}

export function formatInterval(row: MetricRow): string {
  if (row.ci_lo === null || row.ci_hi === null) return '—';
  return `[${formatValue(row.ci_lo, row.unit, true)}, ${formatValue(row.ci_hi, row.unit, true)}]`;
}

export type Verdict = 'significant' | 'not-significant' | 'identical' | 'undefined';

export function verdictOf(row: MetricRow): Verdict {
  if (row.n === 0 || row.significant === null) return 'undefined';
  if (row.identical) return 'identical';
  return row.significant ? 'significant' : 'not-significant';
}

/** The sentence under the numbers; it never hides an interval that crosses zero. */
export function verdictText(row: MetricRow, runs: number): string {
  switch (verdictOf(row)) {
    case 'significant':
      return `significant: the interval excludes 0 (${row.diff! > 0 ? 'B higher' : 'B lower'})`;
    case 'not-significant':
      return `NOT significant with ${row.n} runs: the interval includes 0`;
    case 'identical':
      return 'identical in every run (zero difference)';
    default:
      return row.n < 2 && row.n > 0
        ? 'too few usable runs for an interval'
        : `undefined (no usable pair of ${runs} runs)`;
  }
}

/** Runs where this metric was undefined and so were left out of its interval. */
export const droppedRuns = (row: MetricRow, runs: number): number => runs - row.n;

export function duration(s: number): string {
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} min${s % 60 ? ` ${s % 60} s` : ''}` : `${s} s`;
}
