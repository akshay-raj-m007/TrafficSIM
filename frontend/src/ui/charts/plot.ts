/** Small, dependency-free plotting helpers shared by the canvas charts. */
import { useEffect, useRef, type RefObject } from 'react';

export const PLOT = { left: 48, right: 12, top: 10, bottom: 26 } as const;
export const AXIS_COLOUR = '#8b98a8';
export const GRID_COLOUR = '#222b36';
export const TEXT_FONT = '11px ui-monospace, Consolas, monospace';

/** "Nice" tick values covering [lo, hi] with about `count` steps (1, 2, 5 x 10^k). */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((k) => k * mag).find((s) => s >= raw)!;
  const out: number[] = [];
  const first = Math.ceil(lo / step - 1e-9);
  for (let k = first; k * step <= hi + step * 1e-9; k++)
    out.push(Number((k * step).toPrecision(12)));
  return out;
}

/** Linear map of [d0, d1] onto [r0, r1]. */
export const linear = (d0: number, d1: number, r0: number, r1: number) => (v: number) =>
  d1 === d0 ? r0 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/** Axes with grid lines, tick labels and axis titles inside the plot margins. */
export function drawAxes(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  x: { lo: number; hi: number; title: string },
  y: { lo: number; hi: number; title: string },
): { px: (v: number) => number; py: (v: number) => number } {
  const px = linear(x.lo, x.hi, PLOT.left, w - PLOT.right);
  const py = linear(y.lo, y.hi, h - PLOT.bottom, PLOT.top);
  ctx.font = TEXT_FONT;
  ctx.fillStyle = AXIS_COLOUR;
  ctx.strokeStyle = GRID_COLOUR;
  ctx.lineWidth = 1;
  ctx.textAlign = 'center';
  for (const t of niceTicks(x.lo, x.hi, Math.max(2, Math.floor((w - 60) / 70)))) {
    ctx.beginPath();
    ctx.moveTo(px(t), PLOT.top);
    ctx.lineTo(px(t), h - PLOT.bottom);
    ctx.stroke();
    ctx.fillText(String(t), px(t), h - PLOT.bottom + 12);
  }
  ctx.textAlign = 'right';
  for (const t of niceTicks(y.lo, y.hi, Math.max(2, Math.floor((h - 36) / 34)))) {
    ctx.beginPath();
    ctx.moveTo(PLOT.left, py(t));
    ctx.lineTo(w - PLOT.right, py(t));
    ctx.stroke();
    ctx.fillText(String(t), PLOT.left - 5, py(t) + 3);
  }
  ctx.textAlign = 'right';
  ctx.fillText(x.title, w - PLOT.right, h - 3);
  ctx.textAlign = 'left';
  ctx.fillText(y.title, PLOT.left + 4, PLOT.top + 9);
  return { px, py };
}

/** A canvas that redraws when `deps` change or the element is resized (device-pixel sharp). */
export function useCanvas(
  draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void,
  deps: readonly unknown[],
): RefObject<HTMLCanvasElement | null> {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const render = () => {
      const r = c.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      c.width = Math.max(1, Math.round(r.width * dpr));
      c.height = Math.max(1, Math.round(r.height * dpr));
      const ctx = c.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw(ctx, r.width, r.height);
    };
    render();
    const ro = new ResizeObserver(render);
    ro.observe(c);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}
