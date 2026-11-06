import { memo } from 'react';
import type { KpiMsg, StatsMsg } from '../api/types';
import { KpiPanel } from './KpiPanel';

interface LinkProps {
  rateHz: number;
  rttMs?: number;
  stats: StatsMsg | null;
}

const fmt = (v: number | undefined, digits = 1, unit = '') =>
  v === undefined ? '—' : `${v.toFixed(digits)}${unit}`;

const LinkBlock = memo(function LinkBlock({ rateHz, rttMs, stats }: LinkProps) {
  return (
    <section>
      <h3>Stream (measured)</h3>
      <dl className="facts">
        <dt>Frame rate</dt>
        <dd>{fmt(rateHz, 1, ' Hz')}</dd>
        <dt>Frame size</dt>
        <dd>{stats && stats.frames > 0 ? `${stats.frame_bytes_mean} B` : '—'}</dd>
        <dt>Bandwidth</dt>
        <dd>{stats ? `${(stats.bytes_per_s / 1000).toFixed(1)} KB/s` : '—'}</dd>
        <dt>Server step</dt>
        <dd>{fmt(stats?.step_ms_mean, 2, ' ms')}</dd>
        <dt>Frame encode</dt>
        <dd>{fmt(stats?.encode_ms_mean, 2, ' ms')}</dd>
        <dt>Frame lag</dt>
        <dd>{fmt(stats?.lag_ms, 1, ' ms')}</dd>
        <dt>Round trip</dt>
        <dd>{fmt(rttMs, 0, ' ms')}</dd>
      </dl>
    </section>
  );
});

interface Props extends LinkProps {
  kpi: KpiMsg | null;
  defs: Record<string, string>;
}

export function TelemetryPanel({ kpi, defs, rateHz, rttMs, stats }: Props) {
  return (
    <aside className="panel panel--right">
      <h2>Measured KPIs</h2>
      <KpiPanel kpi={kpi} defs={defs} />
      <LinkBlock rateHz={rateHz} rttMs={rttMs} stats={stats} />
    </aside>
  );
}
