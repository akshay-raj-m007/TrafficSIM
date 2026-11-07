import { useMemo, useState } from 'react';
import { ZONES, type DemandRow, type Problem, type Zone } from '../../api/scenarioTypes';
import {
  checkDemand,
  demandToText,
  destinationsOf,
  odKey,
  originTotal,
  sameRows,
  scaleDemand,
  setOriginTotal,
  type DemandText,
} from '../scenarioDraft';

interface Props {
  live: DemandRow[]; // the demand in force
  errors: Problem[]; // server rejection of the last apply
  disabled: boolean;
  onApply(rows: DemandRow[]): void;
}

const ZONE_NAMES: Record<Zone, string> = {
  W: 'West entry',
  E: 'East entry',
  N1: 'J1 north',
  S1: 'J1 south',
  N2: 'J2 minor road',
};

export function DemandEditor({ live, errors, disabled, onApply }: Props) {
  const [text, setText] = useState<DemandText>(() => demandToText(live));
  const [factor, setFactor] = useState('1.00');
  const check = useMemo(() => checkDemand(text), [text]);
  const changed = check.rows !== null && !sameRows(check.rows, live);
  const set = (k: string, v: string) => setText((t) => ({ ...t, [k]: v }));
  const f = Number(factor);
  const factorOk = /^\d+(\.\d+)?$/.test(factor) && f > 0;

  return (
    <section>
      <h3>
        Demand · veh/h <em>live</em>
      </h3>
      {ZONES.map((o) => {
        const total = originTotal(text, o);
        return (
          <details key={o} className="ed-origin" open={o === 'W' || o === 'E'}>
            <summary>
              {ZONE_NAMES[o]}
              <span className="muted"> {total === null ? '—' : `${Math.round(total)} total`}</span>
            </summary>
            <label className="ed-row">
              <span>total</span>
              <input
                inputMode="decimal"
                value={total === null ? '' : String(Math.round(total * 100) / 100)}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (/^\d+(\.\d+)?$/.test(e.target.value)) {
                    const next = setOriginTotal(text, o, v);
                    if (next) setText(next);
                  }
                }}
                title="Changing the total keeps the destination split"
              />
            </label>
            {destinationsOf(o).map((d) => (
              <label key={d} className="ed-row">
                <span>→ {d}</span>
                <input
                  inputMode="decimal"
                  aria-invalid={!!check.errors[odKey(o, d)]}
                  value={text[odKey(o, d)] ?? ''}
                  onChange={(e) => set(odKey(o, d), e.target.value)}
                />
                {check.errors[odKey(o, d)] && (
                  <span className="ed-error">{check.errors[odKey(o, d)]}</span>
                )}
              </label>
            ))}
          </details>
        );
      })}
      <div className="ed-inline">
        <label className="ed-row">
          <span>scale all ×</span>
          <input inputMode="decimal" value={factor} onChange={(e) => setFactor(e.target.value)} />
        </label>
        <button type="button" disabled={!factorOk} onClick={() => setText(scaleDemand(text, f))}>
          Scale
        </button>
      </div>
      {!factorOk && <p className="ed-error">scale factor must be a number &gt; 0</p>}
      {errors.map((e) => (
        <p key={e.path + e.message} className="ed-error">
          {e.path}: {e.message}
        </p>
      ))}
      <button
        type="button"
        disabled={disabled || !changed}
        onClick={() => check.rows && onApply(check.rows)}
      >
        Apply demand
      </button>
    </section>
  );
}
