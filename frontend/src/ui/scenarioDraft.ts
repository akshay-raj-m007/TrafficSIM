/**
 * Draft logic of the scenario editor (pure, no React): text fields -> validated values.
 *
 * Nothing is clamped or silently corrected: a field that is not a number >= 0, or a mix
 * that does not add up to exactly 100, is an error shown next to the field and the
 * Apply button stays disabled. The server validates again with the same rules.
 */
import {
  CLASS_KEYS,
  ZONES,
  type ClassKey,
  type DemandRow,
  type Mix,
  type Policy,
  type Problem,
  type ScenarioDoc,
  type Zone,
} from '../api/scenarioTypes';

export const MIX_SUM_TOLERANCE = 1e-6; // percent, as in the backend

/** A non-negative decimal number, or null. "1e3", "-1", "", "12abc" are all null. */
export function parseStrictNumber(text: string): number | null {
  const t = text.trim();
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

const fmt = (v: number): string => String(Math.round(v * 100) / 100);

// ---- vehicle mix --------------------------------------------------------------------
export type MixText = Record<ClassKey, string>;

export const mixToText = (m: Mix): MixText =>
  Object.fromEntries(CLASS_KEYS.map((k) => [k, fmt(m[k])])) as MixText;

export interface MixCheck {
  mix: Mix | null;
  total: number | null;
  error: string | null;
}

export function checkMix(t: MixText): MixCheck {
  const values = {} as Mix;
  for (const k of CLASS_KEYS) {
    const v = parseStrictNumber(t[k]);
    if (v === null) return { mix: null, total: null, error: `${k}: enter a number ≥ 0` };
    values[k] = v;
  }
  const total = CLASS_KEYS.reduce((s, k) => s + values[k], 0);
  if (Math.abs(total - 100) > MIX_SUM_TOLERANCE) {
    return {
      mix: null,
      total,
      error: `shares sum to ${fmt(total)}, must be exactly 100`,
    };
  }
  return { mix: values, total, error: null };
}

// ---- demand -------------------------------------------------------------------------
export type DemandText = Record<string, string>; // key "O>D"

export const odKey = (o: Zone, d: Zone): string => `${o}>${d}`;
export const destinationsOf = (o: Zone): Zone[] => ZONES.filter((z) => z !== o);

export function demandToText(rows: DemandRow[]): DemandText {
  const out: DemandText = {};
  for (const o of ZONES) for (const d of destinationsOf(o)) out[odKey(o, d)] = '0';
  for (const r of rows) out[odKey(r.origin, r.destination)] = fmt(r.veh_per_h);
  return out;
}

export interface DemandCheck {
  rows: DemandRow[] | null;
  errors: Record<string, string>;
}

export function checkDemand(t: DemandText): DemandCheck {
  const errors: Record<string, string> = {};
  const rows: DemandRow[] = [];
  for (const o of ZONES) {
    for (const d of destinationsOf(o)) {
      const v = parseStrictNumber(t[odKey(o, d)] ?? '');
      if (v === null) errors[odKey(o, d)] = 'enter a number ≥ 0';
      else if (v > 0) rows.push({ origin: o, destination: d, veh_per_h: v });
    }
  }
  return { rows: Object.keys(errors).length ? null : rows, errors };
}

export function originTotal(t: DemandText, o: Zone): number | null {
  let total = 0;
  for (const d of destinationsOf(o)) {
    const v = parseStrictNumber(t[odKey(o, d)] ?? '');
    if (v === null) return null;
    total += v;
  }
  return total;
}

/** Multiply every flow by `factor` (an exact product, shown to 0.01 veh/h). */
export function scaleDemand(t: DemandText, factor: number): DemandText {
  const out: DemandText = {};
  for (const [k, text] of Object.entries(t)) {
    const v = parseStrictNumber(text);
    out[k] = v === null ? text : fmt(v * factor);
  }
  return out;
}

/** Set one origin's total, keeping its destination split. Null if the origin has no demand
 *  to split (then the split must be typed first). */
export function setOriginTotal(t: DemandText, o: Zone, total: number): DemandText | null {
  const cur = originTotal(t, o);
  if (cur === null || cur === 0) return null;
  return scaleOrigin(t, o, total / cur);
}

function scaleOrigin(t: DemandText, o: Zone, factor: number): DemandText {
  const out = { ...t };
  for (const d of destinationsOf(o)) {
    const v = parseStrictNumber(t[odKey(o, d)] ?? '');
    if (v !== null) out[odKey(o, d)] = fmt(v * factor);
  }
  return out;
}

export function sameRows(a: DemandRow[], b: DemandRow[]): boolean {
  const key = (r: DemandRow) => `${r.origin}>${r.destination}`;
  const ma = new Map(a.filter((r) => r.veh_per_h > 0).map((r) => [key(r), r.veh_per_h]));
  const mb = new Map(b.filter((r) => r.veh_per_h > 0).map((r) => [key(r), r.veh_per_h]));
  return ma.size === mb.size && [...ma].every(([k, v]) => mb.get(k) === v);
}

// ---- the live state of a document -----------------------------------------------------
export interface LiveState {
  demand: DemandRow[];
  mix: Mix;
  policy: Policy;
  flyoverOpen: boolean;
}

/** The settings in force: the initial ones with every logged change applied in order. */
export function currentLive(doc: ScenarioDoc): LiveState {
  const s: LiveState = {
    demand: doc.initial.demand,
    mix: doc.initial.mix,
    policy: doc.initial.policy,
    flyoverOpen: doc.initial.flyover_open,
  };
  for (const c of doc.changes) {
    if (c.type === 'set_demand') s.demand = c.demand;
    else if (c.type === 'set_mix') s.mix = c.mix;
    else if (c.type === 'set_policy') s.policy = c.policy;
    else s.flyoverOpen = c.open;
  }
  return s;
}

/** Server messages whose path starts with `prefix` (e.g. "mix", "demand.3"). */
export const problemsAt = (errors: Problem[], prefix: string): Problem[] =>
  errors.filter((e) => e.path === prefix || e.path.startsWith(`${prefix}.`));

/** The document that restarts the run with the settings in force now (the change log is
 *  folded into the initial settings), the given seed and structure. */
export function restartDoc(
  doc: ScenarioDoc,
  structure: ScenarioDoc['structure'],
  seed: number,
): ScenarioDoc {
  const live = currentLive(doc);
  return {
    ...doc,
    seed,
    structure: { ...structure },
    initial: {
      demand: live.demand,
      mix: live.mix,
      policy: live.policy,
      flyover_open: live.flyoverOpen,
    },
    changes: [],
  };
}

export const isSeed = (text: string): boolean => {
  const v = Number(text);
  return /^\d+$/.test(text) && Number.isSafeInteger(v) && v <= 2 ** 32 - 1;
};
