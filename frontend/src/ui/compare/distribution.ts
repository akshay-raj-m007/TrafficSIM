import type { Distribution } from '../../api/compareTypes';

/** Share of the completed trips [%] in each bin, and in the overflow (slower than the last
 *  bin edge). Computed from the backend's pooled counts; empty distributions give zeros. */
export function binShares(d: Distribution): { bins: number[]; overflow: number } {
  const total = d.n;
  if (total === 0) return { bins: d.counts.map(() => 0), overflow: 0 };
  return {
    bins: d.counts.map((c) => (100 * c) / total),
    overflow: (100 * d.overflow) / total,
  };
}

/** Largest bin share over both sides (the common y range of the histograms). */
export function maxShare(a: Distribution, b: Distribution): number {
  return Math.max(0, ...binShares(a).bins, ...binShares(b).bins);
}
