import { useRef, useState } from 'react';
import type { ScenarioDoc } from '../../api/scenarioTypes';
import type { PresetInfo } from '../editor/SeedBar';

export interface Picked {
  source: string; // "preset:default" | "current" | "file"
  doc: ScenarioDoc | null;
}

interface Props {
  label: string;
  presets: Record<string, PresetInfo>;
  current: ScenarioDoc | null; // the editor's settings in force now
  value: Picked;
  onChange(v: Picked): void;
}

export function ScenarioPicker({ label, presets, current, value, onChange }: Props) {
  const file = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = (source: string) => {
    if (source === 'file') return file.current?.click();
    if (source === 'current') return onChange({ source, doc: current });
    onChange({ source, doc: presets[source.replace('preset:', '')]?.scenario ?? null });
  };

  return (
    <fieldset className="cmp-picker">
      <legend>{label}</legend>
      <select
        value={value.source}
        onChange={(e) => choose(e.target.value)}
        aria-label={`${label} scenario`}
      >
        {Object.keys(presets).map((n) => (
          <option key={n} value={`preset:${n}`}>
            preset · {n.replace(/_/g, ' ')}
          </option>
        ))}
        <option value="current" disabled={!current}>
          current settings of the editor
        </option>
        <option value="file">{fileName ? `file · ${fileName}` : 'imported JSON file…'}</option>
      </select>
      <input
        ref={file}
        type="file"
        accept="application/json,.json"
        hidden
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          try {
            const doc = JSON.parse(await f.text()) as ScenarioDoc;
            setFileName(f.name);
            setError(null);
            onChange({ source: 'file', doc });
          } catch (err) {
            setError(`not valid JSON: ${err instanceof Error ? err.message : String(err)}`);
          }
          e.target.value = '';
        }}
      />
      {error && <p className="ed-error">{error}</p>}
      {value.doc && (
        <p className="hint">
          {value.doc.name} · seed replaced per run · structure J2{' '}
          {value.doc.structure.j2_minor_lanes} lane(s)
        </p>
      )}
    </fieldset>
  );
}
