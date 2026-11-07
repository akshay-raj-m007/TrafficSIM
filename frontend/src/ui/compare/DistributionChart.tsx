import type { Distribution } from '../../api/compareTypes';
import { drawAxes, PLOT, TEXT_FONT, useCanvas } from '../charts/plot';
import { binShares, maxShare } from './distribution';

const COLOUR_A = '#22d3ee';
const COLOUR_B = '#fbbf24';
const BOX_H = 14;

function box(
  ctx: CanvasRenderingContext2D,
  d: Distribution,
  px: (v: number) => number,
  y: number,
  colour: string,
) {
  if (!d.box) return;
  const b = d.box;
  ctx.strokeStyle = colour;
  ctx.fillStyle = colour;
  ctx.lineWidth = 1.5;
  ctx.beginPath(); // whiskers: min to max
  ctx.moveTo(px(b.min), y);
  ctx.lineTo(px(b.max), y);
  ctx.moveTo(px(b.min), y - 4);
  ctx.lineTo(px(b.min), y + 4);
  ctx.moveTo(px(b.max), y - 4);
  ctx.lineTo(px(b.max), y + 4);
  ctx.stroke();
  ctx.globalAlpha = 0.35;
  ctx.fillRect(px(b.q1), y - BOX_H / 2, px(b.q3) - px(b.q1), BOX_H);
  ctx.globalAlpha = 1;
  ctx.strokeRect(px(b.q1), y - BOX_H / 2, px(b.q3) - px(b.q1), BOX_H);
  ctx.beginPath(); // median and p90
  ctx.moveTo(px(b.median), y - BOX_H / 2);
  ctx.lineTo(px(b.median), y + BOX_H / 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(px(b.p90), y, 3, 0, 2 * Math.PI);
  ctx.fill();
}

/** Travel times of the completed trips of A and B, pooled over the runs (backend numbers):
 *  histograms in % of the completed trips of each side, and box plots (min, quartiles, median,
 *  max; the dot is p90). Completed trips only: trips still under way at the end are missing, so
 *  when many trips do not finish both distributions are cut off on the right. */
export function DistributionChart({ a, b }: { a: Distribution; b: Distribution }) {
  const ref = useCanvas(
    (ctx, w, h) => {
      const histH = h - 52;
      const xMax = a.counts.length * a.bin_s;
      const { px, py } = drawAxes(
        ctx,
        w,
        histH + PLOT.bottom,
        { lo: 0, hi: xMax, title: 'travel time [s]' },
        { lo: 0, hi: Math.max(5, maxShare(a, b) * 1.1), title: '% of completed trips per 10 s' },
      );
      const draw = (d: Distribution, colour: string) => {
        ctx.fillStyle = colour;
        ctx.globalAlpha = 0.45;
        binShares(d).bins.forEach((s, i) => {
          if (s > 0) ctx.fillRect(px(i * d.bin_s), py(s), px(d.bin_s) - px(0) - 1, py(0) - py(s));
        });
        ctx.globalAlpha = 1;
      };
      draw(a, COLOUR_A);
      draw(b, COLOUR_B);
      box(ctx, a, px, histH + PLOT.bottom + 12, COLOUR_A);
      box(ctx, b, px, histH + PLOT.bottom + 32, COLOUR_B);
      ctx.font = TEXT_FONT;
      ctx.textAlign = 'right';
      ctx.fillStyle = COLOUR_A;
      ctx.fillText(`A  n=${a.n}`, w - PLOT.right, 22);
      ctx.fillStyle = COLOUR_B;
      ctx.fillText(`B  n=${b.n}`, w - PLOT.right, 36);
    },
    [a, b],
  );
  return (
    <div className="cmp-dist">
      <canvas ref={ref} className="cmp-dist__canvas" data-testid="distribution-chart" />
      <p className="hint">
        Travel time of completed trips, all runs pooled. Box: quartiles and median, whiskers min to
        max, dot p90. Trips unfinished at the end are not in it.
      </p>
    </div>
  );
}
