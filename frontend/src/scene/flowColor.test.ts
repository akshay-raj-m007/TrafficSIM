import { describe, expect, it } from 'vitest';
import {
  FLOW_COLOUR_MAX_VEH_H,
  FLOW_STOPS,
  FLOW_UNUSED_COLOUR,
  FLOW_UNUSED_VEH_H,
  flowColour,
  flowGradientCss,
} from './flowColor';

const hex = (c: [number, number, number]) =>
  (Math.round(c[0] * 255) << 16) | (Math.round(c[1] * 255) << 8) | Math.round(c[2] * 255);

describe('flowColour', () => {
  it('marks a segment below the unused threshold in the unused colour', () => {
    expect(hex(flowColour(0))).toBe(FLOW_UNUSED_COLOUR);
    expect(hex(flowColour(FLOW_UNUSED_VEH_H - 0.1))).toBe(FLOW_UNUSED_COLOUR);
  });
  it('hits the stop colours exactly and saturates at the top of the scale', () => {
    for (const [v, c] of FLOW_STOPS) expect(hex(flowColour(v))).toBe(c);
    expect(hex(flowColour(10 * FLOW_COLOUR_MAX_VEH_H))).toBe(FLOW_STOPS.at(-1)![1]);
  });
  it('blends linearly between two stops', () => {
    const [v0, c0] = FLOW_STOPS[1]!;
    const [v1, c1] = FLOW_STOPS[2]!;
    const mid = flowColour((v0 + v1) / 2);
    const expected = (shift: number) => (((c0 >> shift) & 255) + ((c1 >> shift) & 255)) / 2 / 255;
    expect(mid[0]).toBeCloseTo(expected(16), 6);
    expect(mid[1]).toBeCloseTo(expected(8), 6);
    expect(mid[2]).toBeCloseTo(expected(0), 6);
  });
  it('draws a legend gradient from 0 to 100 %', () => {
    const css = flowGradientCss();
    expect(css).toContain(' 0%');
    expect(css).toContain(' 100%');
  });
});
