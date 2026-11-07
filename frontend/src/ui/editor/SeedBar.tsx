import { useRef, useState } from 'react';
import type { Problem, ScenarioDoc } from '../../api/scenarioTypes';
import { isSeed } from '../scenarioDraft';

export interface PresetInfo {
  info: string;
  scenario: ScenarioDoc;
}

interface Props {
  seed: number; // seed of the running scenario
  presets: Record<string, PresetInfo>;
  preset: string; // the dropdown choice, kept by the parent so a restart does not reset it
  onChoosePreset(name: string): void;
  errors: Problem[]; // server rejection of the last reset / import
  disabled: boolean;
  onReset(seed: number): void;
  onPreset(name: string, seed: number | null): void;
  onExport(): void;
  onImport(doc: unknown): void;
}

export function SeedBar({
  seed,
  presets,
  preset,
  onChoosePreset,
  errors,
  disabled,
  onReset,
  onPreset,
  onExport,
  onImport,
}: Props) {
  const [seedText, setSeedText] = useState('');
  const [fileError, setFileError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const text = seedText === '' ? String(seed) : seedText;
  const ok = isSeed(text);

  const readFile = async (f: File | undefined) => {
    if (!f) return;
    setFileError(null);
    try {
      onImport(JSON.parse(await f.text()));
    } catch (e) {
      setFileError(`not valid JSON: ${e instanceof Error ? e.message : String(e)}`);
    }
    if (file.current) file.current.value = '';
  };

  return (
    <section>
      <label className="field">
        <span>Seed</span>
        <input
          aria-label="Seed"
          inputMode="numeric"
          aria-invalid={!ok}
          value={text}
          onChange={(e) => setSeedText(e.target.value.trim())}
        />
      </label>
      {!ok && <p className="ed-error">seed must be a whole number from 0 to 4294967295</p>}
      <button type="button" disabled={disabled || !ok} onClick={() => onReset(Number(text))}>
        Reset with these settings
      </button>
      <p className="hint">Same seed + same settings + same change log ⇒ identical run.</p>
      <label className="field">
        <span>Preset</span>
        <select value={preset} aria-label="Preset" onChange={(e) => onChoosePreset(e.target.value)}>
          {Object.keys(presets).map((n) => (
            <option key={n} value={n}>
              {n.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </label>
      <p className="hint">{presets[preset]?.info}</p>
      <button
        type="button"
        disabled={disabled || !presets[preset]}
        onClick={() => onPreset(preset, seedText === '' || !ok ? null : Number(text))}
      >
        Load preset (restarts)
      </button>
      <div className="ed-inline">
        <button type="button" disabled={disabled} onClick={onExport}>
          Export JSON
        </button>
        <button type="button" disabled={disabled} onClick={() => file.current?.click()}>
          Import JSON
        </button>
        <input
          ref={file}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => void readFile(e.target.files?.[0])}
        />
      </div>
      {fileError && <p className="ed-error">{fileError}</p>}
      {errors.map((e) => (
        <p key={e.path + e.message} className="ed-error">
          {e.path}: {e.message}
        </p>
      ))}
    </section>
  );
}
