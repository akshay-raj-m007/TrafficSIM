import { memo } from 'react';
import type { KpiMsg } from '../api/types';

interface Props {
  kpi: KpiMsg | null;
  defs: Record<string, string>;
}

const STATE_LABEL = { green: 'green', amber: 'amber', all_red: 'all red' } as const;
const num = (v: number | null | undefined, digits = 1, unit = '') =>
  v === null || v === undefined ? '—' : `${v.toFixed(digits)}${unit}`;

export const KpiPanel = memo(function KpiPanel({ kpi, defs }: Props) {
  if (!kpi) {
    return (
      <section className="placeholder">
        <p>Waiting for the first measurements…</p>
      </section>
    );
  }
  const sig = kpi.signal;
  const d = kpi.delay;
  return (
    <>
      <section>
        <h3 title={defs.signal}>Signal {sig?.junction ?? 'J1'}</h3>
        {sig ? (
          <p className="signal">
            <span className={`lamp lamp--${sig.state}`} />
            phase {sig.phase + 1}/{sig.n_phases} · {sig.approach.replace('_in', '')} ·{' '}
            {STATE_LABEL[sig.state]} {sig.elapsed_s.toFixed(1)} s
            <br />
            <span className="muted">
              {sig.controller}
              {sig.cycle_s ? ` · cycle ${sig.cycle_s} s` : ''}
            </span>
          </p>
        ) : (
          <p className="muted">no signal control in this session</p>
        )}
      </section>

      <section>
        <h3 title={defs.flow}>
          Flow <em>last 60 s</em>
        </h3>
        <table className="kpi">
          <thead>
            <tr>
              <th>detector</th>
              <th>veh/h</th>
              <th>total</th>
            </tr>
          </thead>
          <tbody>
            {kpi.flow.map((f) => (
              <tr key={f.id} title={`${f.in_window} vehicles in the window; 1 vehicle = 60 veh/h`}>
                <td>{f.label}</td>
                <td>{f.veh_per_h}</td>
                <td>{f.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3 title={defs.queue}>Queues at stop lines</h3>
        <table className="kpi">
          <thead>
            <tr>
              <th>approach</th>
              <th>veh</th>
              <th>now</th>
              <th>max 60 s</th>
            </tr>
          </thead>
          <tbody>
            {kpi.queues.map((q) => (
              <tr key={q.id}>
                <td>{q.label}</td>
                <td>{q.veh}</td>
                <td>{q.length_m.toFixed(0)} m</td>
                <td>{q.max_window_m.toFixed(0)} m</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3 title={defs.delay}>Delay vs free flow</h3>
        {d.reference_ready ? (
          <dl className="facts">
            <dt>mean, all exits</dt>
            <dd>
              {num(d.mean_s, 1, ' s')} <span className="muted">n={d.n}</span>
            </dd>
            <dt>mean, last 5 min</dt>
            <dd>
              {num(d.recent_mean_s, 1, ' s')} <span className="muted">n={d.recent_n}</span>
            </dd>
            <dt>entry-queue wait</dt>
            <dd>{num(d.entry_wait_mean_s, 1, ' s')}</dd>
          </dl>
        ) : (
          <p className="muted">free-flow reference not ready yet</p>
        )}
      </section>

      <section>
        <h3 title={defs.unserved}>Unserved demand</h3>
        <dl className="facts">
          <dt>waiting to enter</dt>
          <dd>{kpi.unserved.queued} veh</dd>
          <dt>oldest wait</dt>
          <dd>{kpi.unserved.oldest_wait_s.toFixed(1)} s</dd>
          <dt>generated / inserted</dt>
          <dd>
            {kpi.counts.generated} / {kpi.counts.inserted}
          </dd>
          <dt>exited / on network</dt>
          <dd>
            {kpi.counts.exited} / {kpi.counts.active}
          </dd>
        </dl>
      </section>
    </>
  );
});
