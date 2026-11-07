import type { VehicleClassInfo } from '../api/types';
import {
  FLOW_COLOUR_MAX_VEH_H,
  FLOW_UNUSED_COLOUR,
  FLOW_UNUSED_VEH_H,
  flowGradientCss,
} from '../scene/flowColor';
import { SPEED_COLOUR_MAX_KMH, speedGradientCss } from '../scene/speedColor';

const TICKS = [0, 20, 40, 60];
const CLASS_LABEL: Record<string, string> = {
  car: 'car',
  truck_bus: 'truck / bus',
  two_wheeler: 'two-wheeler',
  cav: 'CAV',
};

const FLOW_TICKS = [0, 400, 800, FLOW_COLOUR_MAX_VEH_H];

export function Legend({ classes, laneFlow }: { classes: VehicleClassInfo[]; laneFlow: boolean }) {
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
      {laneFlow && (
        <div className="legend__block" data-testid="lane-flow-legend">
          <span className="legend__title">lane flow</span>
          <span
            className="legend__swatch"
            style={{ background: `#${FLOW_UNUSED_COLOUR.toString(16)}` }}
            title={`under ${FLOW_UNUSED_VEH_H} veh/h`}
          />
          <span>unused</span>
          <div className="legend__ramp" style={{ background: flowGradientCss() }} />
          <span>{FLOW_TICKS.join(' · ')} veh/h (last 5 min)</span>
        </div>
      )}
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
