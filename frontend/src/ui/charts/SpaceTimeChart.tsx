import { useState } from 'react';
import { speedColour } from '../../scene/speedColor';
import type { ChartStore } from './chartStore';
import { AXIS_COLOUR, drawAxes, TEXT_FONT, useCanvas } from './plot';

const NO_DATA_RGB = [16, 21, 27] as const;

/** Speed colour per cell for one corridor, one pixel per (second, cell), y up = downstream. */
function speedImage(store: ChartStore, key: string, cells: number): ImageData | null {
  const n = store.cols.length;
  if (n === 0 || cells === 0) return null;
  const img = new ImageData(n, cells);
  for (let col = 0; col < n; col++) {
    for (let cell = 0; cell < cells; cell++) {
      const v = store.speed(key, col, cell);
      const [r, g, b] = v === null ? NO_DATA_RGB : speedColour(v).map((c) => Math.round(c * 255));
      const o = ((cells - 1 - cell) * n + col) * 4;
      img.data[o] = r!;
      img.data[o + 1] = g!;
      img.data[o + 2] = b!;
      img.data[o + 3] = 255;
    }
  }
  return img;
}

/** Space-time diagram of the W-E corridor: speed (Edie, 10 m x 1 s cells). Queues are the red
 *  bands; a jam that spreads upstream leans toward lower positions as time goes on. */
export function SpaceTimeChart({ store, version }: { store: ChartStore; version: number }) {
  const [dir, setDir] = useState<'eastbound' | 'westbound'>('eastbound');
  const [route, setRoute] = useState<'surface' | 'flyover'>('surface');
  const key = `${dir}_${route}`;
  const corridor = store.corridors.find((c) => c.key === key);
  const ref = useCanvas(
    (ctx, w, h) => {
      const len = corridor?.length_m ?? 1000;
      const t0 = store.col0;
      const t1 = t0 + Math.max(store.cols.length, 60);
      const { px, py } = drawAxes(
        ctx,
        w,
        h,
        { lo: t0, hi: t1, title: 'simulated time [s]' },
        { lo: 0, hi: len, title: `position along ${dir} ${route} [m]` },
      );
      const img = corridor ? speedImage(store, key, corridor.cells) : null;
      if (img) {
        const off = new OffscreenCanvas(img.width, img.height);
        off.getContext('2d')!.putImageData(img, 0, 0);
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(
          off,
          px(t0),
          py(img.height * store.cellM),
          px(t0 + img.width) - px(t0),
          py(0) - py(img.height * store.cellM),
        );
      }
      ctx.font = TEXT_FONT;
      ctx.fillStyle = AXIS_COLOUR;
      ctx.textAlign = 'left';
      for (const m of corridor?.marks ?? []) {
        ctx.strokeStyle = AXIS_COLOUR;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(px(t0), py(m.x_m));
        ctx.lineTo(px(t1), py(m.x_m));
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillText(m.id, px(t0) + 4, py(m.x_m) - 3);
      }
    },
    [version, key],
  );
  const pick = <T extends string>(v: T, set: (x: T) => void, all: readonly T[]) => (
    <span role="group">
      {all.map((x) => (
        <button key={x} type="button" className={x === v ? 'is-active' : ''} onClick={() => set(x)}>
          {x}
        </button>
      ))}
    </span>
  );
  return (
    <div className="chart__spacetime">
      <div className="chart__controls">
        {pick(dir, setDir, ['eastbound', 'westbound'] as const)}
        {pick(route, setRoute, ['surface', 'flyover'] as const)}
        <span className="chart__ramp" title="speed 0 to 60 km/h: red = stopped, cyan = free flow" />
        <span>0 → 60 km/h</span>
      </div>
      <canvas ref={ref} className="chart__canvas" data-testid="chart-spacetime" />
    </div>
  );
}
