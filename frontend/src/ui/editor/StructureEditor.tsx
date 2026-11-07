import type { Problem } from '../../api/scenarioTypes';

interface Props {
  running: 1 | 2; // the J2 minor approach of the running network
  value: 1 | 2;
  errors: Problem[];
  onChange(v: 1 | 2): void;
}

export function StructureEditor({ running, value, errors, onChange }: Props) {
  return (
    <section>
      <h3>
        Structure <em>applies on reset</em>
      </h3>
      <label className="field">
        <span>J2 minor approach</span>
        <select value={value} onChange={(e) => onChange(Number(e.target.value) as 1 | 2)}>
          <option value={2}>2 lanes: left lane + right lane</option>
          <option value={1}>1 shared lane (old layout)</option>
        </select>
      </label>
      {value !== running && (
        <p className="ed-badge" role="status">
          pending until reset (running: {running === 1 ? '1 shared lane' : '2 turn lanes'})
        </p>
      )}
      {errors.map((e) => (
        <p key={e.path + e.message} className="ed-error">
          {e.path}: {e.message}
        </p>
      ))}
      <p className="hint">
        Lane counts and widths of the main roads are not editable yet (planned).
      </p>
    </section>
  );
}
