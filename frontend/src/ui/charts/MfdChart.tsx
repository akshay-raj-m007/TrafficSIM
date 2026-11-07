import type { ChartStore } from './chartStore';
import { drawAxes, TEXT_FONT, useCanvas } from './plot';

/** Flyover open / closed at the end of each 10 s window (the colours the legend shows). */
export const MFD_OPEN = '#22d3ee';
export const MFD_CLOSED = '#fbbf24';

/** Network flow against density, one point per 10 s window (Edie, per lane); the newest
 *  points are the most opaque, so a closure shows as a shift of the cloud and of its colour. */
export function MfdChart({ store, version }: { store: ChartStore; version: number }) {
  const ref = useCanvas(
    (ctx, w, h) => {
      const pts = store.mfd;
      const kMax = Math.max(20, ...pts.map((p) => p.density)) * 1.05;
      const qMax = Math.max(400, ...pts.map((p) => p.flow)) * 1.1;
      const { px, py } = drawAxes(
        ctx,
        w,
        h,
        { lo: 0, hi: kMax, title: 'density [veh/km/lane]' },
        { lo: 0, hi: qMax, title: 'flow [veh/h/lane]' },
      );
      pts.forEach((p, i) => {
        const age = (i + 1) / pts.length; // 0 = oldest, 1 = newest
        ctx.globalAlpha = 0.25 + 0.75 * age;
        ctx.fillStyle = p.flyoverOpen ? MFD_OPEN : MFD_CLOSED;
        ctx.beginPath();
        ctx.arc(px(p.density), py(p.flow), i === pts.length - 1 ? 5 : 3, 0, 2 * Math.PI);
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      ctx.font = TEXT_FONT;
      ctx.textAlign = 'left';
      ctx.fillStyle = MFD_OPEN;
      ctx.fillText('● flyover open', w - 250, 22);
      ctx.fillStyle = MFD_CLOSED;
      ctx.fillText('● flyover closed', w - 140, 22);
    },
    [version],
  );
  return <canvas ref={ref} className="chart__canvas" data-testid="chart-mfd" />;
}
