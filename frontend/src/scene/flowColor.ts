/**
 * Lane colour by measured flow (the "Lane flow" overlay): the arrivals on a lane or junction
 * connector over the last 5 min, scaled to veh/h (backend engine/laneflow.py). A fixed scale
 * so two runs can be compared by eye; the legend draws the same stops.
 *
 * Below FLOW_UNUSED_VEH_H the segment is marked "unused" in magenta, the same threshold the
 * utilisation report and test use (backend engine/utilisation.py MIN_ARRIVALS_H).
 */
export const FLOW_UNUSED_VEH_H = 5;
/** Top of the scale: about the flow of a busy lane in this model (one lane saturates near
 *  1,500-1,900 veh/h at a signal); everything above shows the top colour. */
export const FLOW_COLOUR_MAX_VEH_H = 1200;
export const FLOW_UNUSED_COLOUR = 0xd946ef;

/** [veh/h, sRGB hex] stops, linearly interpolated in sRGB: dark blue -> teal -> yellow -> orange. */
export const FLOW_STOPS: readonly (readonly [number, number])[] = [
  [FLOW_UNUSED_VEH_H, 0x1e3a8a],
  [400, 0x0d9488],
  [800, 0xfacc15],
  [FLOW_COLOUR_MAX_VEH_H, 0xf97316],
];

const channel = (hex: number, shift: number) => (hex >> shift) & 255;
const rgb = (hex: number): [number, number, number] => [
  channel(hex, 16) / 255,
  channel(hex, 8) / 255,
  channel(hex, 0) / 255,
];

/** sRGB colour (0..1 per channel) for a flow in veh/h. */
export function flowColour(vehPerH: number): [number, number, number] {
  if (vehPerH < FLOW_UNUSED_VEH_H) return rgb(FLOW_UNUSED_COLOUR);
  const q = Math.min(vehPerH, FLOW_COLOUR_MAX_VEH_H);
  for (let i = 1; i < FLOW_STOPS.length; i++) {
    const [v1, c1] = FLOW_STOPS[i]!;
    const [v0, c0] = FLOW_STOPS[i - 1]!;
    if (q <= v1) {
      const u = (q - v0) / (v1 - v0);
      const a = rgb(c0);
      const b = rgb(c1);
      return [a[0] * (1 - u) + b[0] * u, a[1] * (1 - u) + b[1] * u, a[2] * (1 - u) + b[2] * u];
    }
  }
  return rgb(FLOW_STOPS[FLOW_STOPS.length - 1]![1]);
}

/** CSS gradient for the legend (the ramp only, from FLOW_UNUSED_VEH_H up). */
export function flowGradientCss(): string {
  const span = FLOW_COLOUR_MAX_VEH_H - FLOW_UNUSED_VEH_H;
  const stops = FLOW_STOPS.map(
    ([v, c]) => `#${c.toString(16).padStart(6, '0')} ${((v - FLOW_UNUSED_VEH_H) / span) * 100}%`,
  );
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}
