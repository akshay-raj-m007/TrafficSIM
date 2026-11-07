/**
 * Draft logic of the structure editor (pure): lane counts and widths of the two lane groups.
 * Same ranges as the backend (network/structure.py); nothing is clamped, an out-of-range or
 * malformed value is an error next to its field and the reset stays disabled.
 */
import type { StructureDoc } from '../api/scenarioTypes';

export const LANES_RANGE = [1, 4] as const;
export const WIDTH_RANGE_M = [2.5, 4.0] as const;
/** Below this width the lane-width speed model extrapolates (HCM reference lane width). */
export const WIDTH_MODEL_REFERENCE_M = 3.05;

export const DEFAULT_STRUCTURE: StructureDoc = {
  j2_minor_lanes: 2,
  surface_lanes: 2,
  flyover_lanes: 2,
  surface_width_m: 3.5,
  flyover_width_m: 3.5,
};

export interface StructureText {
  j2_minor_lanes: string;
  surface_lanes: string;
  flyover_lanes: string;
  surface_width_m: string;
  flyover_width_m: string;
}

export type StructureErrors = Partial<Record<keyof StructureText, string>>;

export const structureToText = (s: StructureDoc): StructureText => ({
  j2_minor_lanes: String(s.j2_minor_lanes),
  surface_lanes: String(s.surface_lanes),
  flyover_lanes: String(s.flyover_lanes),
  surface_width_m: String(s.surface_width_m),
  flyover_width_m: String(s.flyover_width_m),
});

function lanes(name: string, text: string, lo: number, hi: number): [number | null, string | null] {
  const v = /^\d+$/.test(text.trim()) ? Number(text) : NaN;
  return Number.isInteger(v) && v >= lo && v <= hi
    ? [v, null]
    : [null, `${name} ${text === '' ? '(empty)' : text} is outside ${lo}..${hi} (whole lanes)`];
}

function width(name: string, text: string): [number | null, string | null] {
  const v = /^\d+(\.\d+)?$/.test(text.trim()) ? Number(text) : NaN;
  const [lo, hi] = WIDTH_RANGE_M;
  return v >= lo && v <= hi
    ? [v, null]
    : [
        null,
        `${name} ${text === '' ? '(empty)' : `${text} m`} is outside ${lo}..${hi.toFixed(1)} m`,
      ];
}

export function checkStructure(t: StructureText): {
  structure: StructureDoc | null;
  errors: StructureErrors;
} {
  const errors: StructureErrors = {};
  const [j2, e1] = lanes('j2_minor_lanes', t.j2_minor_lanes, 1, 2);
  const [s, e2] = lanes('surface_lanes', t.surface_lanes, ...LANES_RANGE);
  const [f, e3] = lanes('flyover_lanes', t.flyover_lanes, ...LANES_RANGE);
  const [ws, e4] = width('surface_width_m', t.surface_width_m);
  const [wf, e5] = width('flyover_width_m', t.flyover_width_m);
  if (e1) errors.j2_minor_lanes = e1;
  if (e2) errors.surface_lanes = e2;
  if (e3) errors.flyover_lanes = e3;
  if (e4) errors.surface_width_m = e4;
  if (e5) errors.flyover_width_m = e5;
  if (Object.keys(errors).length) return { structure: null, errors };
  return {
    structure: {
      j2_minor_lanes: j2 as 1 | 2,
      surface_lanes: s!,
      flyover_lanes: f!,
      surface_width_m: ws!,
      flyover_width_m: wf!,
    },
    errors,
  };
}

export const sameStructure = (a: StructureDoc, b: StructureDoc): boolean =>
  (Object.keys(a) as (keyof StructureDoc)[]).every((k) => a[k] === b[k]);

/** Widths below the lane-width model's reference width (the speed model extrapolates there). */
export const extrapolated = (s: StructureDoc): boolean =>
  s.surface_width_m < WIDTH_MODEL_REFERENCE_M || s.flyover_width_m < WIDTH_MODEL_REFERENCE_M;
