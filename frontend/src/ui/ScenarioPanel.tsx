import { useMemo, useState } from 'react';
import type { NetworkData } from '../api/types';
import { summarise } from './networkSummary';

interface Props {
  network: NetworkData | null;
  seed?: number;
  disabled: boolean;
  onReset(seed: number): void;
}

export function ScenarioPanel({ network, seed, disabled, onReset }: Props) {
  const [seedText, setSeedText] = useState('');
  const summary = useMemo(() => (network ? summarise(network) : null), [network]);
  const parsed = Number.parseInt(seedText || String(seed ?? 42), 10);
  const seedValid = Number.isInteger(parsed) && parsed >= 0 && parsed <= 2 ** 32 - 1;

  return (
    <aside className="panel panel--left">
      <h2>Scenario</h2>
      <section>
        <label className="field">
          <span>Random seed</span>
          <input
            inputMode="numeric"
            placeholder={String(seed ?? 42)}
            value={seedText}
            onChange={(e) => setSeedText(e.target.value.replace(/[^0-9]/g, ''))}
          />
        </label>
        <button type="button" disabled={disabled || !seedValid} onClick={() => onReset(parsed)}>
          Reset simulation
        </button>
        <p className="hint">Same seed + scenario ⇒ identical results.</p>
      </section>

      <section className="placeholder" aria-disabled>
        <h3>Demand <em>step 2</em></h3>
        <p>Origin–destination flows (veh/h) per zone: W, E, N1, S1, N2.</p>
        <h3>Vehicle mix <em>step 2</em></h3>
        <p>Car · truck/bus · two-wheeler · CAV shares.</p>
        <h3>Signal control <em>step 2</em></h3>
        <p>Fixed-time (Webster cycle) or adaptive max-pressure at J1.</p>
      </section>

      {summary && (
        <section>
          <h3>Network (measured from geometry)</h3>
          <dl className="facts">
            <dt>Roads / lanes</dt>
            <dd>
              {summary.roads} / {summary.lanes}
            </dd>
            <dt>Lane-km</dt>
            <dd>{summary.laneKm.toFixed(2)}</dd>
            <dt>Lanes per road</dt>
            <dd>{summary.laneCounts.join(', ')}</dd>
            <dt>Lane widths</dt>
            <dd>{summary.laneWidths.map((w) => `${w} m`).join(', ')}</dd>
            <dt>Flyover deck</dt>
            <dd>
              {summary.flyoverLengthM.toFixed(0)} m at +{summary.deckZ} m
            </dd>
            {summary.junctions.map((j) => (
              <div key={j.id} className="facts__row">
                <dt>{j.id}</dt>
                <dd>
                  {j.control}, {j.movements} movements
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </aside>
  );
}
