import type { Problem, StructureDoc } from '../../api/scenarioTypes';
import {
  LANES_RANGE,
  WIDTH_MODEL_REFERENCE_M,
  WIDTH_RANGE_M,
  extrapolated,
  sameStructure,
  type StructureErrors,
  type StructureText,
} from '../structureDraft';

interface Props {
  running: StructureDoc; // the structure of the running network
  text: StructureText; // the draft (applies on reset)
  draft: StructureDoc | null; // the draft if valid
  errors: StructureErrors;
  serverErrors: Problem[];
  onChange(t: StructureText): void;
}

const LANE_OPTIONS = Array.from({ length: LANES_RANGE[1] - LANES_RANGE[0] + 1 }, (_, i) => i + 1);

export function StructureEditor({ running, text, draft, errors, serverErrors, onChange }: Props) {
  const set = (k: keyof StructureText, v: string) => onChange({ ...text, [k]: v });
  const group = (title: string, lanes: keyof StructureText, width: keyof StructureText) => (
    <fieldset className="ed-group">
      <legend>{title}</legend>
      <label className="ed-row">
        <span>lanes / direction</span>
        <select
          value={text[lanes]}
          aria-label={`${title} lanes`}
          onChange={(e) => set(lanes, e.target.value)}
        >
          {LANE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label className="ed-row">
        <span>lane width, m</span>
        <input
          inputMode="decimal"
          aria-label={`${title} lane width`}
          aria-invalid={!!errors[width]}
          value={text[width]}
          onChange={(e) => set(width, e.target.value)}
        />
      </label>
      {errors[lanes] && <p className="ed-error">{errors[lanes]}</p>}
      {errors[width] && <p className="ed-error">{errors[width]}</p>}
    </fieldset>
  );
  const pending = draft !== null && !sameStructure(draft, running);

  return (
    <section>
      <h3>
        Structure <em>applies on reset</em>
      </h3>
      {group('Surface road (through J1)', 'surface_lanes', 'surface_width_m')}
      {group('Flyover / through road', 'flyover_lanes', 'flyover_width_m')}
      <label className="field">
        <span>J2 minor approach</span>
        <select
          value={text.j2_minor_lanes}
          aria-label="J2 minor approach"
          onChange={(e) => set('j2_minor_lanes', e.target.value)}
        >
          <option value="2">2 lanes: left lane + right lane</option>
          <option value="1">1 shared lane (old layout)</option>
        </select>
      </label>
      {errors.j2_minor_lanes && <p className="ed-error">{errors.j2_minor_lanes}</p>}
      {pending && (
        <p className="ed-badge" role="status">
          pending until reset (running: {running.surface_lanes}+{running.flyover_lanes} lanes,{' '}
          {running.surface_width_m}/{running.flyover_width_m} m, J2 {running.j2_minor_lanes})
        </p>
      )}
      {draft && extrapolated(draft) && (
        <p className="hint">
          Below {WIDTH_MODEL_REFERENCE_M} m the lane-width speed model extrapolates.
        </p>
      )}
      {serverErrors.map((e) => (
        <p key={e.path + e.message} className="ed-error">
          {e.path}: {e.message}
        </p>
      ))}
      <p className="hint">
        West arterial = surface + flyover lanes; east of J1 the surface lanes continue as link lanes
        (same count and width) that join the flyover lanes at the merge. Lanes {LANES_RANGE[0]}–
        {LANES_RANGE[1]}, widths {WIDTH_RANGE_M[0]}–{WIDTH_RANGE_M[1].toFixed(1)} m.
      </p>
    </section>
  );
}
