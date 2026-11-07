import { formatClock } from '../../api/protocol';
import type { LoggedChange } from '../../api/scenarioTypes';

function describe(c: LoggedChange): string {
  switch (c.type) {
    case 'set_demand':
      return `demand: ${Math.round(c.demand.reduce((s, r) => s + r.veh_per_h, 0))} veh/h in total`;
    case 'set_mix':
      return `mix: ${c.mix.car}/${c.mix.truck_bus}/${c.mix.two_wheeler}/${c.mix.cav} %`;
    case 'set_policy':
      return `signal policy: ${c.policy}`;
    case 'set_flyover':
      return c.open ? 'flyover opened' : 'flyover closed';
  }
}

export function ChangeLog({
  changes,
  stepsPerSecond,
}: {
  changes: LoggedChange[];
  stepsPerSecond: number;
}) {
  return (
    <section>
      <h3>Change log</h3>
      {changes.length === 0 ? (
        <p className="hint">No live changes yet.</p>
      ) : (
        <ol className="ed-log">
          {changes.map((c, i) => (
            <li key={i}>
              <span className="muted">
                tick {c.tick} · {formatClock(c.tick, stepsPerSecond).slice(3)}
              </span>{' '}
              {describe(c)}
            </li>
          ))}
        </ol>
      )}
      <p className="hint">Same seed + same log ⇒ identical run.</p>
    </section>
  );
}
