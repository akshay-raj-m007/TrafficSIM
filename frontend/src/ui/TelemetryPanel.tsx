import type { LiveState } from '../App';

const fmt = (v: number | undefined, digits = 1, unit = '') =>
  v === undefined ? '—' : `${v.toFixed(digits)}${unit}`;

export function TelemetryPanel({ live }: { live: LiveState }) {
  const t = live.tick;
  return (
    <aside className="panel panel--right">
      <h2>Telemetry</h2>
      <section>
        <h3>Simulation</h3>
        <dl className="facts">
          <dt>Tick</dt>
          <dd>{t?.tick ?? '—'}</dd>
          <dt>Sim time</dt>
          <dd>{fmt(t?.t, 1, ' s')}</dd>
          <dt>Speed</dt>
          <dd>{t ? (t.speed === 0 ? 'paused' : `${t.speed}×`) : '—'}</dd>
          <dt>Time step</dt>
          <dd>{live.hello ? `${live.hello.dt} s (fixed)` : '—'}</dd>
          <dt>Seed</dt>
          <dd>{live.hello?.seed ?? '—'}</dd>
        </dl>
      </section>
      <section>
        <h3>Link (measured)</h3>
        <dl className="facts">
          <dt>Frame rate</dt>
          <dd>{fmt(live.rateHz, 1, ' Hz')}</dd>
          <dt>Server step cost</dt>
          <dd>{fmt(t?.step_ms, 3, ' ms')}</dd>
          <dt>Frame lag</dt>
          <dd>{fmt(t?.lag_ms, 1, ' ms')}</dd>
          <dt>Round trip</dt>
          <dd>{fmt(live.rttMs, 0, ' ms')}</dd>
        </dl>
      </section>
      <section className="placeholder">
        <h3>KPIs <em>step 2</em></h3>
        <p>All measured, never estimated:</p>
        <ul>
          <li>Flow — detector-line crossings (veh/h)</li>
          <li>Queue length — from vehicle positions (m)</li>
          <li>Delay — actual − free-flow travel time (s)</li>
          <li>Unserved demand — blocked spawns</li>
        </ul>
      </section>
    </aside>
  );
}
