import { describe, expect, it } from 'vitest';
import type { ChartsMsg } from '../../api/messageTypes';
import { ChartStore, HISTORY_S } from './chartStore';

const b64 = (bytes: number[]) => btoa(String.fromCharCode(...bytes));
const msg = (over: Partial<ChartsMsg>): ChartsMsg => ({
  type: 'charts',
  col0: 0,
  cell_m: 10,
  corridors: [
    { key: 'a', label: 'a', cells: 2, length_m: 20, marks: [] },
    { key: 'b', label: 'b', cells: 3, length_m: 30, marks: [] },
  ],
  speed_unit_mps: 0.1,
  no_data: 255,
  cols: [],
  mfd: [],
  queue: [],
  ...over,
});

describe('ChartStore', () => {
  it('decodes columns, keeps corridors back to back and maps 255 to no data', () => {
    const s = new ChartStore();
    s.push(msg({ cols: [b64([10, 255, 100, 20, 255])] }));
    expect(s.speed('a', 0, 0)).toBeCloseTo(1.0);
    expect(s.speed('a', 0, 1)).toBeNull();
    expect(s.speed('b', 0, 0)).toBeCloseTo(10.0);
    expect(s.speed('b', 0, 2)).toBeNull();
    expect(s.offset('b')).toBe(2);
  });

  it('appends increments and drops the history older than the window', () => {
    const s = new ChartStore();
    const col = b64([0, 0, 0, 0, 0]);
    s.push(msg({ cols: Array(HISTORY_S).fill(col) }));
    s.push(msg({ col0: HISTORY_S, cols: [col, col, col] }));
    expect(s.cols.length).toBe(HISTORY_S);
    expect(s.col0).toBe(3);
  });

  it('starts again when the server restarts the history', () => {
    const s = new ChartStore();
    const col = b64([0, 0, 0, 0, 0]);
    s.push(msg({ cols: [col, col, col] }));
    s.push(msg({ col0: 0, cols: [col] }));
    expect(s.cols.length).toBe(1);
    expect(s.col0).toBe(0);
  });

  it('stores MFD and queue points exactly as sent', () => {
    const s = new ChartStore();
    s.push(msg({ mfd: [[10, 8.3, 315.7, true]], queue: [[1, 17.8, 20.8]] }));
    expect(s.mfd[0]).toEqual({ t: 10, density: 8.3, flow: 315.7, flyoverOpen: true });
    expect(s.queue[0]).toEqual({ t: 1, j1: 17.8, j2: 20.8 });
  });
});
