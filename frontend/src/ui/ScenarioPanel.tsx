import { useMemo, useState } from 'react';
import type {
  LiveChange,
  LoggedChange,
  Policy,
  Problem,
  ScenarioDoc,
} from '../api/scenarioTypes';
import type { NetworkData } from '../api/types';
import { ChangeLog } from './editor/ChangeLog';
import { DemandEditor } from './editor/DemandEditor';
import { LiveControls } from './editor/LiveControls';
import { MixEditor } from './editor/MixEditor';
import { SeedBar, type PresetInfo } from './editor/SeedBar';
import { StructureEditor } from './editor/StructureEditor';
import { summarise } from './networkSummary';
import { currentLive, problemsAt, restartDoc } from './scenarioDraft';

export interface ScenarioEditorProps {
  network: NetworkData | null;
  doc: ScenarioDoc | null; // the scenario in force, change log included
  epoch: number; // bumps on every (re)start: drafts reload
  presets: Record<string, PresetInfo>;
  applyErrors: Problem[];
  resetErrors: Problem[];
  stepsPerSecond: number;
  disabled: boolean;
  onApply(change: LiveChange): void;
  onResetTo(doc: ScenarioDoc): void;
  onPreset(name: string, seed: number | null): void;
  onExport(): void;
  onImport(doc: unknown): void;
}

/** Drafts live in this component; the parent keys it by epoch so a restart reloads them. */
export function ScenarioPanel(p: ScenarioEditorProps) {
  return <ScenarioPanelBody key={p.epoch} {...p} />;
}

function ScenarioPanelBody(p: ScenarioEditorProps) {
  const { doc } = p;
  const [j2, setJ2] = useState<1 | 2>(doc?.structure.j2_minor_lanes ?? 2);
  const summary = useMemo(() => (p.network ? summarise(p.network) : null), [p.network]);
  const live = doc ? currentLive(doc) : null;
  const changes: LoggedChange[] = doc?.changes ?? [];

  return (
    <aside className="panel panel--left">
      <h2>Scenario{doc ? ` · ${doc.name}` : ''}</h2>
      {!doc || !live ? (
        <p className="hint">
          This session runs an experiment-only setup (query parameters); the editor needs a scenario
          document. Use a preset to switch.
        </p>
      ) : null}
      <SeedBar
        seed={doc?.seed ?? 42}
        presets={p.presets}
        errors={p.resetErrors}
        disabled={p.disabled}
        onReset={(seed) => doc && p.onResetTo(restartDoc(doc, j2, seed))}
        onPreset={p.onPreset}
        onExport={p.onExport}
        onImport={p.onImport}
      />
      {doc && live && (
        <>
          <StructureEditor
            running={doc.structure.j2_minor_lanes}
            value={j2}
            errors={problemsAt(p.resetErrors, 'structure')}
            onChange={setJ2}
          />
          <DemandEditor
            live={live.demand}
            errors={problemsAt(p.applyErrors, 'demand')}
            disabled={p.disabled}
            onApply={(demand) => p.onApply({ type: 'set_demand', demand })}
          />
          <MixEditor
            live={live.mix}
            errors={problemsAt(p.applyErrors, 'mix')}
            disabled={p.disabled}
            onApply={(mix) => p.onApply({ type: 'set_mix', mix })}
          />
          <LiveControls
            policy={live.policy}
            flyoverOpen={live.flyoverOpen}
            signalled
            errors={p.applyErrors.filter((e) => /^(policy|open|change)/.test(e.path))}
            disabled={p.disabled}
            onPolicy={(policy: Policy) => p.onApply({ type: 'set_policy', policy })}
            onFlyover={(open) => p.onApply({ type: 'set_flyover', open })}
          />
          <ChangeLog changes={changes} stepsPerSecond={p.stepsPerSecond} />
        </>
      )}
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
          </dl>
        </section>
      )}
    </aside>
  );
}
