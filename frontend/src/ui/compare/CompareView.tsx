import { useEffect, useRef, useState } from 'react';
import {
  RejectedError,
  cancelCompare,
  fetchExperiment,
  fetchExperiments,
  fetchLimits,
  pollCompare,
  startCompare,
} from '../../api/compareApi';
import type { ExperimentDoc, ExperimentInfo, Job, Limits } from '../../api/compareTypes';
import type { Problem, ScenarioDoc } from '../../api/scenarioTypes';
import type { PresetInfo } from '../editor/SeedBar';
import { ResultsTable } from './ResultsTable';
import { ScenarioPicker, type Picked } from './ScenarioPicker';

interface Props {
  presets: Record<string, PresetInfo>;
  current: ScenarioDoc | null;
}

const num = (t: string): number | null => (/^\d+(\.\d+)?$/.test(t) ? Number(t) : null);

export function CompareView({ presets, current }: Props) {
  const [limits, setLimits] = useState<Limits | null>(null);
  const [experiments, setExperiments] = useState<ExperimentInfo[]>([]);
  const [experiment, setExperiment] = useState<ExperimentDoc | null>(null);
  const [a, setA] = useState<Picked>({ source: 'preset:default', doc: null });
  const [b, setB] = useState<Picked>({ source: 'preset:rush_hour', doc: null });
  const [runs, setRuns] = useState(5);
  const [duration, setDuration] = useState('900');
  const [warmup, setWarmup] = useState('300');
  const [baseSeed, setBaseSeed] = useState('1');
  const [job, setJob] = useState<Job | null>(null);
  const [errors, setErrors] = useState<Problem[]>([]);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    fetchLimits()
      .then(setLimits)
      .catch(() => setLimits(null));
    fetchExperiments()
      .then(setExperiments)
      .catch(() => setExperiments([]));
  }, []);
  useEffect(() => () => window.clearInterval(timer.current), []);

  const docA = a.doc ?? presets[a.source.replace('preset:', '')]?.scenario ?? null;
  const docB = b.doc ?? presets[b.source.replace('preset:', '')]?.scenario ?? null;

  const poll = (id: string) => {
    window.clearInterval(timer.current);
    timer.current = window.setInterval(() => {
      pollCompare(id)
        .then((j) => {
          setJob(j);
          if (j.state !== 'running') window.clearInterval(timer.current);
        })
        .catch(() => window.clearInterval(timer.current));
    }, 1000);
  };

  const run = async () => {
    setErrors([]);
    setExperiment(null);
    const d = num(duration);
    const w = num(warmup);
    const s = num(baseSeed);
    const bad: Problem[] = [];
    if (!docA || !docB) bad.push({ path: 'scenario', message: 'choose both scenarios' });
    if (d === null) bad.push({ path: 'duration', message: 'enter a number of seconds' });
    if (w === null) bad.push({ path: 'warm-up', message: 'enter a number of seconds' });
    if (s === null) bad.push({ path: 'base seed', message: 'enter a whole number' });
    if (bad.length || !docA || !docB) return setErrors(bad);
    try {
      const j = await startCompare({
        a: docA,
        b: docB,
        runs,
        duration_s: d!,
        warmup_s: w!,
        base_seed: s!,
      });
      setJob(j);
      if (j.state === 'running') poll(j.id);
    } catch (e) {
      setErrors(e instanceof RejectedError ? e.errors : [{ path: 'request', message: String(e) }]);
    }
  };

  const running = job?.state === 'running';
  return (
    <main className="compare">
      <section className="cmp-settings">
        <h2>Compare scenarios A and B</h2>
        <div className="cmp-pickers">
          <ScenarioPicker label="A" presets={presets} current={current} value={a} onChange={setA} />
          <ScenarioPicker label="B" presets={presets} current={current} value={b} onChange={setB} />
        </div>
        <div className="cmp-run">
          <label className="field">
            <span>Runs (paired seeds)</span>
            <select value={runs} onChange={(e) => setRuns(Number(e.target.value))}>
              {(limits?.runs ?? [3, 5, 10]).map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Duration, s</span>
            <input
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              inputMode="decimal"
            />
          </label>
          <label className="field">
            <span>Warm-up excluded, s</span>
            <input value={warmup} onChange={(e) => setWarmup(e.target.value)} inputMode="decimal" />
          </label>
          <label className="field">
            <span>Base seed</span>
            <input
              value={baseSeed}
              onChange={(e) => setBaseSeed(e.target.value)}
              inputMode="numeric"
            />
          </label>
          <button type="button" disabled={running} onClick={() => void run()}>
            Run comparison
          </button>
        </div>
        <p className="hint">
          Run i of A and B share seed base + i. Warm-up default 300 s: longer than the longest
          free-flow trip (242 s). Server limits: up to {limits?.runs.at(-1) ?? '…'} runs,{' '}
          {limits?.max_duration_s ?? '…'} s.
        </p>
        {errors.map((e) => (
          <p key={e.path + e.message} className="ed-error">
            {e.path}: {e.message}
          </p>
        ))}
        {job && job.state !== 'done' && (
          <div className="cmp-progress">
            <progress value={job.done} max={job.total} />
            <span>
              {job.state === 'running' ? 'running' : job.state} · {job.done}/{job.total} runs
              {job.cached ? ` (${job.cached} cached)` : ''} · {job.elapsed_s.toFixed(0)} s
            </span>
            {running && (
              <button type="button" onClick={() => void cancelCompare(job.id)}>
                Cancel
              </button>
            )}
            {job.error && <p className="ed-error">{job.error}</p>}
          </div>
        )}
        <h3>Built-in experiments (precomputed, 10 runs)</h3>
        <div className="cmp-exps">
          {experiments.map((x) => (
            <button
              key={x.id}
              type="button"
              disabled={!x.available}
              title={x.description}
              onClick={() => {
                setJob(null);
                void fetchExperiment(x.id).then(setExperiment);
              }}
            >
              {x.title}
              {x.stale ? ' (stale)' : ''}
            </button>
          ))}
        </div>
      </section>
      <section className="cmp-results">
        {job?.result && <ResultsTable result={job.result} />}
        {experiment && (
          <>
            <h2>{experiment.title}</h2>
            <p className="hint">{experiment.description}</p>
            {experiment.stale && (
              <p className="ed-error">
                These stored results are stale (the model changed since they were generated).
              </p>
            )}
            {experiment.comparisons.map((c) => (
              <ResultsTable key={c.label} result={c.result} title={c.label} />
            ))}
          </>
        )}
        {!job?.result && !experiment && (
          <p className="hint">Pick two scenarios and run, or open a built-in experiment.</p>
        )}
      </section>
    </main>
  );
}
