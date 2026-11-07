import { describe, expect, it } from 'vitest';
import type { ScenarioDoc } from '../api/scenarioTypes';
import {
  checkDemand,
  checkMix,
  currentLive,
  demandToText,
  mixToText,
  originTotal,
  isSeed,
  parseStrictNumber,
  restartDoc,
  sameRows,
  scaleDemand,
  setOriginTotal,
} from './scenarioDraft';
import { DEFAULT_STRUCTURE } from './structureDraft';

const MIX = { car: 55, truck_bus: 10, two_wheeler: 30, cav: 5 };

describe('strict numbers: nothing is guessed', () => {
  it('accepts plain non-negative decimals only', () => {
    expect(parseStrictNumber('12')).toBe(12);
    expect(parseStrictNumber(' 0.5 ')).toBe(0.5);
    for (const bad of ['', '-1', '1e3', '12abc', '1,5', 'NaN', 'Infinity', '.5', '5.'])
      expect(parseStrictNumber(bad), bad).toBeNull();
  });
});

describe('vehicle mix must add up to exactly 100', () => {
  it('passes the default and says why otherwise, without clamping', () => {
    expect(checkMix(mixToText(MIX))).toEqual({
      mix: MIX,
      total: 100,
      error: null,
    });
    const t = { ...mixToText(MIX), car: '52' };
    const r = checkMix(t);
    expect(r.mix).toBeNull();
    expect(r.error).toBe('shares sum to 97, must be exactly 100');
    expect(checkMix({ ...mixToText(MIX), cav: '5x' }).error).toBe('cav: enter a number ≥ 0');
    expect(checkMix({ ...mixToText(MIX), car: '55.01' }).mix).toBeNull(); // 0.01 off is an error
  });
});

describe('demand table', () => {
  const rows = [
    { origin: 'W', destination: 'E', veh_per_h: 1100 },
    { origin: 'W', destination: 'N1', veh_per_h: 200 },
    { origin: 'E', destination: 'W', veh_per_h: 900 },
  ] as const;
  const text = demandToText([...rows]);

  it('has every ordered zone pair and drops zero rows when converting back', () => {
    expect(Object.keys(text)).toHaveLength(20);
    const c = checkDemand(text);
    expect(c.errors).toEqual({});
    expect(c.rows).toEqual([...rows]);
  });

  it('reports each bad field by its pair and returns no rows', () => {
    const c = checkDemand({ ...text, 'W>E': '-5', 'N1>S1': 'many' });
    expect(c.rows).toBeNull();
    expect(Object.keys(c.errors).sort()).toEqual(['N1>S1', 'W>E']);
  });

  it('scales everything, or one origin keeping its destination split', () => {
    const x = scaleDemand(text, 1.5);
    expect(x['W>E']).toBe('1650');
    expect(x['E>W']).toBe('1350');
    expect(originTotal(text, 'W')).toBe(1300);
    const y = setOriginTotal(text, 'W', 650)!;
    expect(y['W>E']).toBe('550');
    expect(y['W>N1']).toBe('100');
    expect(y['E>W']).toBe('900'); // other origins untouched
    expect(setOriginTotal(text, 'N2', 100)).toBeNull(); // nothing to split
  });

  it('compares tables ignoring zero rows and order', () => {
    expect(sameRows([...rows], [rows[2], rows[0], rows[1]])).toBe(true);
    expect(sameRows([...rows], [rows[0], rows[1]])).toBe(false);
  });
});

describe('the live state of a document is the initial one plus its change log', () => {
  const doc: ScenarioDoc = {
    version: 1,
    name: 'x',
    seed: 1,
    duration_s: 60,
    structure: DEFAULT_STRUCTURE,
    initial: {
      demand: [{ origin: 'W', destination: 'E', veh_per_h: 100 }],
      mix: MIX,
      policy: 'fixed_webster',
      flyover_open: true,
    },
    changes: [
      { tick: 10, type: 'set_flyover', open: false },
      { tick: 20, type: 'set_policy', policy: 'max_pressure' },
      { tick: 30, type: 'set_flyover', open: true },
      {
        tick: 40,
        type: 'set_mix',
        mix: { car: 100, truck_bus: 0, two_wheeler: 0, cav: 0 },
      },
    ],
  };
  it('replays in order', () => {
    const s = currentLive(doc);
    expect(s.flyoverOpen).toBe(true);
    expect(s.policy).toBe('max_pressure');
    expect(s.mix.car).toBe(100);
    expect(s.demand).toHaveLength(1);
  });
});

describe('restarting folds the change log into the initial settings', () => {
  it('keeps the settings in force, drops the log, takes the new seed and structure', () => {
    const doc: ScenarioDoc = {
      version: 1,
      name: 'x',
      seed: 1,
      duration_s: 60,
      structure: DEFAULT_STRUCTURE,
      initial: {
        demand: [],
        mix: MIX,
        policy: 'fixed_webster',
        flyover_open: true,
      },
      changes: [{ tick: 5, type: 'set_flyover', open: false }],
    };
    const r = restartDoc(doc, { ...DEFAULT_STRUCTURE, j2_minor_lanes: 1 }, 77);
    expect(r.changes).toEqual([]);
    expect(r.initial.flyover_open).toBe(false);
    expect([r.seed, r.structure.j2_minor_lanes]).toEqual([77, 1]);
  });
  it('accepts only whole-number seeds in range', () => {
    expect(isSeed('0') && isSeed('4294967295')).toBe(true);
    for (const bad of ['', '-1', '1.5', '4294967296', 'abc']) expect(isSeed(bad), bad).toBe(false);
  });
});
