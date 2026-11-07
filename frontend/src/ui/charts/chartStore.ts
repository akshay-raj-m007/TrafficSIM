/**
 * The chart data of one session, merged from the server's `charts` messages. Nothing is
 * computed here: columns, MFD points and queue samples are stored as measured by the backend
 * (engine/charts.py); the store only keeps the last HISTORY_S seconds and decodes the speed
 * columns from base64.
 */
import type { ChartCorridor, ChartsMsg } from '../../api/messageTypes';

export const HISTORY_S = 600;

export interface MfdPoint {
  t: number;
  density: number; // veh/km/lane
  flow: number; // veh/h/lane
  flyoverOpen: boolean;
}
export interface QueuePoint {
  t: number;
  j1: number;
  j2: number;
}

function decode(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export class ChartStore {
  corridors: ChartCorridor[] = [];
  cellM = 10;
  speedUnitMps = 0.1;
  noData = 255;
  /** Absolute index (= seconds) of cols[0]. */
  col0 = 0;
  cols: Uint8Array[] = []; // all corridors back to back, one entry per second
  mfd: MfdPoint[] = [];
  queue: QueuePoint[] = [];
  version = 0;

  clear(): void {
    this.corridors = [];
    this.col0 = 0;
    this.cols = [];
    this.mfd = [];
    this.queue = [];
    this.version++;
  }

  push(m: ChartsMsg): void {
    this.corridors = m.corridors;
    this.cellM = m.cell_m;
    this.speedUnitMps = m.speed_unit_mps;
    this.noData = m.no_data;
    if (this.cols.length === 0) this.col0 = m.col0;
    // a gap (or a restart of the history) makes the old columns meaningless
    else if (m.col0 !== this.col0 + this.cols.length) {
      this.cols = [];
      this.col0 = m.col0;
    }
    for (const c of m.cols) this.cols.push(decode(c));
    const drop = this.cols.length - HISTORY_S;
    if (drop > 0) {
      this.cols.splice(0, drop);
      this.col0 += drop;
    }
    for (const [t, density, flow, flyoverOpen] of m.mfd) {
      this.mfd.push({ t, density, flow, flyoverOpen });
    }
    for (const [t, j1, j2] of m.queue) this.queue.push({ t, j1, j2 });
    if (this.mfd.length > HISTORY_S) this.mfd.splice(0, this.mfd.length - HISTORY_S);
    if (this.queue.length > HISTORY_S) this.queue.splice(0, this.queue.length - HISTORY_S);
    this.version++;
  }

  /** Start offset of a corridor inside a column (corridors are stored back to back). */
  offset(key: string): number {
    let at = 0;
    for (const c of this.corridors) {
      if (c.key === key) return at;
      at += c.cells;
    }
    return -1;
  }

  /** Speed [m/s] of a cell, or null where no vehicle was in it. */
  speed(key: string, col: number, cell: number): number | null {
    const o = this.offset(key);
    const c = this.cols[col];
    if (o < 0 || !c) return null;
    const v = c[o + cell]!;
    return v === this.noData ? null : v * this.speedUnitMps;
  }
}
