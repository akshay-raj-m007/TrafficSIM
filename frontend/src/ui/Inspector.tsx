import type { VehicleLiveMsg } from '../api/messageTypes';

const CLASS_LABEL: Record<string, string> = {
  car: 'car',
  truck_bus: 'truck / bus',
  two_wheeler: 'two-wheeler',
  cav: 'CAV',
};
const kmh = (mps: number) => (mps * 3.6).toFixed(1);

interface Props {
  v: VehicleLiveMsg | null;
  /** Set once the vehicle has left the network: when (simulated seconds), else null. */
  goneAt: { t: number | null; laneChanges: number } | null;
  follow: boolean;
  onFollow(): void;
  onClose(): void;
}

/** Everything the engine knows about the selected vehicle (server/inspector.py). */
export function Inspector({ v, goneAt, follow, onFollow, onClose }: Props) {
  return (
    <aside className="inspector" aria-label="Vehicle inspector" data-testid="inspector">
      <div className="inspector__head">
        <h3>{v ? `Vehicle ${v.vid} · ${CLASS_LABEL[v.class] ?? v.class}` : 'Vehicle'}</h3>
        <button
          type="button"
          className={follow ? 'is-on' : ''}
          aria-pressed={follow}
          disabled={goneAt !== null}
          data-testid="inspector-follow"
          onClick={onFollow}
        >
          follow
        </button>
        <button
          type="button"
          aria-label="Close inspector"
          data-testid="inspector-close"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      {goneAt && (
        <p className="inspector__gone" data-testid="inspector-gone">
          Left the network{goneAt.t !== null ? ` at t = ${goneAt.t.toFixed(1)} s` : ''} after{' '}
          {goneAt.laneChanges} lane change(s). Closing…
        </p>
      )}
      {v && (
        <>
          <dl data-testid="inspector-now">
            <dt>trip</dt>
            <dd>
              {v.origin} → {v.destination}
            </dd>
            <dt>lane</dt>
            <dd>
              {v.lane} at {v.s_m.toFixed(0)} m
            </dd>
            <dt>speed</dt>
            <dd>
              {v.speed_mps.toFixed(1)} m/s ({kmh(v.speed_mps)} km/h)
            </dd>
            <dt>acceleration</dt>
            <dd>{v.acc_mps2.toFixed(2)} m/s²</dd>
            <dt>delay so far</dt>
            <dd title="(now - generated) - free-flow time of this route and class; a lower bound until it exits">
              {v.delay_s === null ? '—' : `${v.delay_s.toFixed(1)} s`}
              {v.free_flow_s !== null && ` (free flow ${v.free_flow_s.toFixed(0)} s)`}
            </dd>
            <dt>lane changes</dt>
            <dd>{v.lane_changes}</dd>
            <dt>route</dt>
            <dd>{v.route.join(' → ')}</dd>
          </dl>
          <h4>IDM (car following)</h4>
          <dl>
            <dt>desired speed v₀</dt>
            <dd>{kmh(v.idm.v0_mps)} km/h</dd>
            <dt>time gap T</dt>
            <dd>{v.idm.T_s} s</dd>
            <dt>max accel a</dt>
            <dd>{v.idm.a_mps2} m/s²</dd>
            <dt>comfort decel b</dt>
            <dd>{v.idm.b_mps2} m/s²</dd>
            <dt>min gap s₀</dt>
            <dd>{v.idm.s0_m} m</dd>
            <dt>size</dt>
            <dd>
              {v.idm.length_m} × {v.idm.width_m} m
            </dd>
          </dl>
          <h4>MOBIL (lane changes, all vehicles)</h4>
          <dl>
            <dt>politeness p</dt>
            <dd>{v.mobil.politeness}</dd>
            <dt>threshold</dt>
            <dd>{v.mobil.threshold_mps2} m/s²</dd>
            <dt>keep-left bias</dt>
            <dd>{v.mobil.keep_left_bias_mps2} m/s²</dd>
            <dt>safe decel b_safe</dt>
            <dd>{v.mobil.b_safe_mps2} m/s²</dd>
            <dt>cooldown</dt>
            <dd>{v.mobil.cooldown_s} s</dd>
          </dl>
        </>
      )}
    </aside>
  );
}
