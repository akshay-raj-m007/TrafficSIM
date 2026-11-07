import { describe, expect, it } from 'vitest';
import type { StructureDoc } from '../api/scenarioTypes';
import { checkStructure, extrapolated, sameStructure, structureToText } from './structureDraft';

const DEFAULT: StructureDoc = {
  j2_minor_lanes: 2,
  surface_lanes: 2,
  flyover_lanes: 2,
  surface_width_m: 3.5,
  flyover_width_m: 3.5,
};

describe('structure draft', () => {
  it('round-trips the default and accepts the extremes', () => {
    expect(checkStructure(structureToText(DEFAULT)).structure).toEqual(DEFAULT);
    const narrow = {
      ...DEFAULT,
      surface_lanes: 1,
      flyover_lanes: 1,
      surface_width_m: 2.5,
      flyover_width_m: 2.5,
    };
    const wide = {
      ...DEFAULT,
      surface_lanes: 4,
      flyover_lanes: 4,
      surface_width_m: 4,
      flyover_width_m: 4,
    };
    expect(checkStructure(structureToText(narrow)).structure).toEqual(narrow);
    expect(checkStructure(structureToText(wide)).structure).toEqual(wide);
  });

  it('names every out-of-range or malformed value and never clamps', () => {
    const t = {
      ...structureToText(DEFAULT),
      surface_lanes: '5',
      flyover_lanes: '1.5',
      surface_width_m: '2.4',
      flyover_width_m: '4.01',
      j2_minor_lanes: '3',
    };
    const r = checkStructure(t);
    expect(r.structure).toBeNull();
    expect(r.errors.surface_lanes).toBe('surface_lanes 5 is outside 1..4 (whole lanes)');
    expect(r.errors.flyover_lanes).toContain('flyover_lanes 1.5 is outside 1..4');
    expect(r.errors.surface_width_m).toBe('surface_width_m 2.4 m is outside 2.5..4.0 m');
    expect(r.errors.flyover_width_m).toBe('flyover_width_m 4.01 m is outside 2.5..4.0 m');
    expect(r.errors.j2_minor_lanes).toContain('outside 1..2');
    expect(
      checkStructure({ ...structureToText(DEFAULT), surface_width_m: '' }).errors.surface_width_m,
    ).toContain('(empty)');
    expect(
      checkStructure({ ...structureToText(DEFAULT), surface_width_m: '3,5' }).structure,
    ).toBeNull();
  });

  it('compares structures, and flags extrapolated widths', () => {
    expect(sameStructure(DEFAULT, { ...DEFAULT })).toBe(true);
    expect(sameStructure(DEFAULT, { ...DEFAULT, flyover_width_m: 3 })).toBe(false);
    expect(extrapolated(DEFAULT)).toBe(false);
    expect(extrapolated({ ...DEFAULT, surface_width_m: 3.0 })).toBe(true);
  });
});
