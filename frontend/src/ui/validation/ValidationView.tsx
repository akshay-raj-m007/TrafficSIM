import { useEffect, useState } from 'react';
import type { ValidationDoc, ValidationItem } from '../../api/validationTypes';
import { verdictClass } from './validationFormat';

function Item({ item }: { item: ValidationItem }) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = (cmd: string) => {
    void navigator.clipboard?.writeText(cmd);
    setCopied(cmd);
  };
  const h = item.headline;
  return (
    <article className="val-item" data-testid="validation-item" id={`val-${item.id}`}>
      <h3>{item.title}</h3>
      <p>{item.what}</p>
      {h ? (
        <div className="val-headline">
          <div>
            <span className="muted">measured</span>
            <strong>
              {h.measured} {h.unit}
            </strong>
            <span className="muted">{h.label}</span>
          </div>
          <div>
            <span className="muted">reference</span>
            <strong>
              {h.reference} {h.unit}
            </strong>
          </div>
          <div className={`val-verdict ${verdictClass(h.verdict)}`}>{h.verdict}</div>
        </div>
      ) : (
        <p className="val-doc">Documented in the README; not recomputed by the tool.</p>
      )}
      {item.table && (
        <table className="val-table">
          <thead>
            <tr>
              {item.table.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {item.table.rows.map((r, i) => (
              <tr key={i}>
                {r.map((v, k) => (
                  <td key={k}>{v === null ? '—' : String(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {item.bullets && (
        <ul>
          {item.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      {item.notes?.map((n) => (
        <p key={n} className="hint">
          {n}
        </p>
      ))}
      <p className="val-ref">
        <span className="muted">reference value: </span>
        {item.reference.text} <span className="muted">Source: </span>
        {item.reference.source}
      </p>
      <div className="val-cmds">
        <span className="muted">reproduce</span>
        {item.commands.map((c) => (
          <div key={c} className="val-cmd">
            <code>{c}</code>
            <button type="button" onClick={() => copy(c)}>
              {copied === c ? 'copied' : 'copy'}
            </button>
          </div>
        ))}
      </div>
    </article>
  );
}

/** The stored validation results (precomputed by backend tools/gen_validation.py; no live runs). */
export function ValidationView() {
  const [doc, setDoc] = useState<ValidationDoc | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    fetch('/api/validation')
      .then((r) =>
        r.ok ? (r.json() as Promise<ValidationDoc>) : Promise.reject(new Error(String(r.status))),
      )
      .then((d) => live && setDoc(d))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, []);
  return (
    <section className="validation" aria-label="Validation results">
      <h2>Validation</h2>
      <p className="hint">
        Stored results of the validation tests: what the model measures, what the literature or the
        HCM says, and the command that reproduces each one. Nothing here is computed live.
      </p>
      {error && <p className="ed-error">Could not load the validation results ({error}).</p>}
      {doc?.stale && (
        <p className="ed-error">
          These results are stale (the engine changed since they were generated): rerun
          tools/gen_validation.py.
        </p>
      )}
      {doc?.items.map((i) => (
        <Item key={i.id} item={i} />
      ))}
    </section>
  );
}
