import { useState } from 'react';
import type { ComparisonResult, MetricRow } from '../../api/compareTypes';
import {
  droppedRuns,
  duration,
  formatInterval,
  formatValue,
  verdictOf,
  verdictText,
} from './tableFormat';

const side = (s: ComparisonResult['meta']['a']) =>
  `${s.name} · demand ${Math.round(s.demand_veh_h)} veh/h · ${s.policy} · flyover ${
    s.flyover_open ? 'open' : 'closed'
  } · J2 ${s.j2_minor_lanes === 1 ? 'shared lane' : '2 lanes'}${
    s.changes ? ` · ${s.changes} live change(s)` : ''
  }`;

function SeedRows({ row, seeds }: { row: MetricRow; seeds: number[] }) {
  return (
    <tr className="cmp-seeds">
      <td colSpan={6}>
        <table>
          <thead>
            <tr>
              <th>seed</th>
              <th>A</th>
              <th>B</th>
              <th>B − A</th>
            </tr>
          </thead>
          <tbody>
            {row.per_seed.map((p, i) => (
              <tr key={seeds[i]}>
                <td>{seeds[i]}</td>
                <td>{formatValue(p.a, row.unit)}</td>
                <td>{formatValue(p.b, row.unit)}</td>
                <td>
                  {p.a === null || p.b === null ? '—' : formatValue(p.b - p.a, row.unit, true)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </td>
    </tr>
  );
}

export function ResultsTable({ result, title }: { result: ComparisonResult; title?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  const m = result.meta;
  return (
    <div className="cmp-result">
      {title && <h3>{title}</h3>}
      <dl className="cmp-meta">
        <dt>A</dt>
        <dd>{side(m.a)}</dd>
        <dt>B</dt>
        <dd>{side(m.b)}</dd>
        <dt>Run</dt>
        <dd>
          {m.runs} paired runs (seeds {m.seeds[0]}–{m.seeds[m.seeds.length - 1]}), duration{' '}
          {duration(m.duration_s)}, warm-up {duration(m.warmup_s)} excluded; paired t, df ={' '}
          {m.runs - 1}
        </dd>
        <dt>Trips</dt>
        <dd>
          per run (mean): A {m.mean_counts.a.completed.toFixed(0)} completed,{' '}
          {m.mean_counts.a.unfinished.toFixed(0)} unfinished · B{' '}
          {m.mean_counts.b.completed.toFixed(0)} completed, {m.mean_counts.b.unfinished.toFixed(0)}{' '}
          unfinished (cohort A {m.mean_counts.a.cohort.toFixed(0)}, B{' '}
          {m.mean_counts.b.cohort.toFixed(0)})
        </dd>
        <dt>Cost</dt>
        <dd>
          the {m.cost.computed_runs + m.cost.cached_runs} runs took {m.cost.run_cpu_s.toFixed(0)}{' '}
          CPU s in total; this request computed {m.cost.computed_runs} ({m.cost.cpu_s.toFixed(0)}{' '}
          CPU s, {m.cost.wall_s.toFixed(0)} s wall on {m.cost.workers} workers) and reused{' '}
          {m.cost.cached_runs} cached
        </dd>
      </dl>
      {!m.paired_arrivals && <p className="ed-error">{m.pairing_note}</p>}
      <p className="hint">
        Overloaded scenarios (queues that keep growing) do not settle: their numbers depend on how
        long you run, so the duration above belongs to every figure below.
      </p>
      <table className="cmp-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>A</th>
            <th>B</th>
            <th>B − A</th>
            <th>95% CI of B − A</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {result.metrics.map((r) => (
            <FragmentRow
              key={r.id}
              row={r}
              runs={m.runs}
              seeds={m.seeds}
              open={open === r.id}
              onToggle={() => setOpen(open === r.id ? null : r.id)}
            />
          ))}
        </tbody>
      </table>
      <p className="hint">{result.note}</p>
    </div>
  );
}

function FragmentRow(p: {
  row: MetricRow;
  runs: number;
  seeds: number[];
  open: boolean;
  onToggle(): void;
}) {
  const { row: r } = p;
  const v = verdictOf(r);
  return (
    <>
      <tr className={`cmp-row cmp-${v}`} onClick={p.onToggle} title="Click for the per-seed values">
        <td>
          {p.open ? '▾' : '▸'} {r.label} <span className="muted">[{r.unit}]</span>
        </td>
        <td>{formatValue(r.mean_a, r.unit)}</td>
        <td>{formatValue(r.mean_b, r.unit)}</td>
        <td>{formatValue(r.diff, r.unit, true)}</td>
        <td>{formatInterval(r)}</td>
        <td>
          {verdictText(r, p.runs)}
          {droppedRuns(r, p.runs) > 0 && r.n > 0 && (
            <span className="muted"> · {droppedRuns(r, p.runs)} run(s) undefined, left out</span>
          )}
        </td>
      </tr>
      {p.open && <SeedRows row={r} seeds={p.seeds} />}
    </>
  );
}
