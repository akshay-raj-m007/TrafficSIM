import type { VehicleClassInfo } from '../api/types';
import { SPEED_COLOUR_MAX_KMH, speedGradientCss } from '../scene/speedColor';

const TICKS = [0, 20, 40, 60];
const CLASS_LABEL: Record<string, string> = {
  car: 'car',
  truck_bus: 'truck / bus',
  two_wheeler: 'two-wheeler',
  cav: 'CAV',
};

export function Legend({ classes }: { classes: VehicleClassInfo[] }) {
  return (
    <div className="viewport__legend">
      <div className="legend__block">
        <span className="legend__title">speed</span>
        <div className="legend__ramp" style={{ background: speedGradientCss() }} />
        <div className="legend__ticks">
          {TICKS.map((t) => (
            <span key={t} style={{ left: `${(t / SPEED_COLOUR_MAX_KMH) * 100}%` }}>
              {t}
            </span>
          ))}
          <span className="legend__unit">km/h</span>
        </div>
      </div>
      <div className="legend__block">
        <span className="lamp-swatch" /> brake light
      </div>
      <div className="legend__block legend__classes">
        {classes.map((c) => (
          <span key={c.name}>
            {CLASS_LABEL[c.name] ?? c.name} {c.length_m}×{c.width_m} m
          </span>
        ))}
      </div>
      <div className="legend__block">
        <span className="dot dot--left" /> left <span className="dot dot--through" /> through{' '}
        <span className="dot dot--right" /> right
      </div>
      <div className="legend__block legend__note">
        1 unit = 1 m · left-hand traffic · grid 100 m
      </div>
    </div>
  );
}
