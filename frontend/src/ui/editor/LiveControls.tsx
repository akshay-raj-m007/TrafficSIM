import type { Policy, Problem } from '../../api/scenarioTypes';

interface Props {
  policy: Policy;
  flyoverOpen: boolean;
  signalled: boolean; // false for experiment-only (uncontrolled) sessions
  errors: Problem[];
  disabled: boolean;
  onPolicy(p: Policy): void;
  onFlyover(open: boolean): void;
}

const POLICIES: { id: Policy; label: string; hint: string }[] = [
  {
    id: 'fixed_webster',
    label: 'Fixed-time (Webster)',
    hint: 'Plan fixed when selected, from the demand then',
  },
  {
    id: 'max_pressure',
    label: 'Max-pressure',
    hint: 'Textbook rule, 7 s minimum green',
  },
  {
    id: 'max_pressure_threshold',
    label: 'Thresholded max-pressure',
    hint: '15 s minimum green, switching threshold from measured losses',
  },
];

export function LiveControls({
  policy,
  flyoverOpen,
  signalled,
  errors,
  disabled,
  onPolicy,
  onFlyover,
}: Props) {
  return (
    <section>
      <h3>
        J1 signal policy <em>live</em>
      </h3>
      {POLICIES.map((p) => (
        <label key={p.id} className="ed-radio" title={p.hint}>
          <input
            type="radio"
            name="policy"
            checked={policy === p.id}
            disabled={disabled || !signalled}
            onChange={() => onPolicy(p.id)}
          />
          {p.label}
        </label>
      ))}
      <p className="hint">A new policy takes over at the next phase boundary.</p>
      <h3>
        Flyover <em>live</em>
      </h3>
      <button
        type="button"
        disabled={disabled}
        className={flyoverOpen ? '' : 'is-active'}
        onClick={() => {
          const msg = flyoverOpen
            ? 'Close the flyover? Vehicles on it finish their trip; everyone else is routed over the surface.'
            : 'Reopen the flyover? New route choices may use it again.';
          if (window.confirm(msg)) onFlyover(!flyoverOpen);
        }}
      >
        {flyoverOpen ? 'Flyover is open · close it' : 'Flyover is closed · reopen it'}
      </button>
      {errors.map((e) => (
        <p key={e.path + e.message} className="ed-error">
          {e.message}
        </p>
      ))}
    </section>
  );
}
