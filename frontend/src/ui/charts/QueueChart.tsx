import type { ChartStore } from './chartStore';
import { drawAxes, TEXT_FONT, useCanvas } from './plot';

export const J1_COLOUR = '#22d3ee';
export const J2_COLOUR = '#f6ad55';

/** Longest approach queue at J1 and J2, one sample per second (engine/queues.py). */
export function QueueChart({ store, version }: { store: ChartStore; version: number }) {
  const ref = useCanvas(
    (ctx, w, h) => {
      const q = store.queue;
      const t0 = q.length ? q[0]!.t : 0;
      const t1 = q.length ? Math.max(q[q.length - 1]!.t, t0 + 60) : 60;
      const yMax = Math.max(50, ...q.map((p) => Math.max(p.j1, p.j2))) * 1.1;
      const { px, py } = drawAxes(
        ctx,
        w,
        h,
        { lo: t0, hi: t1, title: 'simulated time [s]' },
        { lo: 0, hi: yMax, title: 'longest approach queue [m]' },
      );
      const line = (colour: string, pick: (p: (typeof q)[number]) => number) => {
        ctx.strokeStyle = colour;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        q.forEach((p, i) =>
          i ? ctx.lineTo(px(p.t), py(pick(p))) : ctx.moveTo(px(p.t), py(pick(p))),
        );
        ctx.stroke();
      };
      line(J1_COLOUR, (p) => p.j1);
      line(J2_COLOUR, (p) => p.j2);
      ctx.font = TEXT_FONT;
      ctx.textAlign = 'left';
      ctx.fillStyle = J1_COLOUR;
      ctx.fillText('— J1', w - 100, 22);
      ctx.fillStyle = J2_COLOUR;
      ctx.fillText('— J2', w - 50, 22);
    },
    [version],
  );
  return <canvas ref={ref} className="chart__canvas" data-testid="chart-queue" />;
}
