/**
 * Vehicle colour by speed: a fixed 0 – SPEED_COLOUR_MAX_KMH ramp (stopped = red,
 * moderate = amber, free flow = cyan-teal), chosen for contrast on the dark ground. The
 * legend draws the same stops, so what you see is what the legend says.
 */
export const SPEED_COLOUR_MAX_KMH = 60; // the flyover speed limit

/** [km/h, sRGB hex] stops, linearly interpolated in sRGB. */
export const SPEED_STOPS: readonly (readonly [number, number])[] = [
  [0, 0xf43f5e],
  [30, 0xfbbf24],
  [60, 0x22d3ee],
];

const channel = (hex: number, shift: number) => (hex >> shift) & 255;

/** sRGB colour (0..1 per channel) for a speed in m/s. */
export function speedColour(speedMps: number): [number, number, number] {
  const kmh = Math.min(Math.max(speedMps * 3.6, 0), SPEED_COLOUR_MAX_KMH);
  for (let i = 1; i < SPEED_STOPS.length; i++) {
    const [v1, c1] = SPEED_STOPS[i]!;
    const [v0, c0] = SPEED_STOPS[i - 1]!;
    if (kmh <= v1) {
      const u = (kmh - v0) / (v1 - v0);
      const mix = (shift: number) => (channel(c0, shift) * (1 - u) + channel(c1, shift) * u) / 255;
      return [mix(16), mix(8), mix(0)];
    }
  }
  const last = SPEED_STOPS[SPEED_STOPS.length - 1]![1];
  return [channel(last, 16) / 255, channel(last, 8) / 255, channel(last, 0) / 255];
}

/** CSS gradient string matching the ramp (for the legend). */
export function speedGradientCss(): string {
  const stops = SPEED_STOPS.map(
    ([v, c]) => `#${c.toString(16).padStart(6, '0')} ${(v / SPEED_COLOUR_MAX_KMH) * 100}%`,
  );
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}
