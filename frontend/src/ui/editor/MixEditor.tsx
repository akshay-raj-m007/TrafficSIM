import { useMemo, useState } from 'react';
import { CLASS_KEYS, type Mix, type Problem } from '../../api/scenarioTypes';
import { checkMix, mixToText, type MixText } from '../scenarioDraft';

interface Props {
  live: Mix;
  errors: Problem[];
  disabled: boolean;
  onApply(mix: Mix): void;
}

const LABEL = {
  car: 'Car',
  truck_bus: 'Truck / bus',
  two_wheeler: 'Two-wheeler',
  cav: 'CAV',
};

export function MixEditor({ live, errors, disabled, onApply }: Props) {
  const [text, setText] = useState<MixText>(() => mixToText(live));
  const check = useMemo(() => checkMix(text), [text]);
  const changed = check.mix !== null && CLASS_KEYS.some((k) => check.mix![k] !== live[k]);

  return (
    <section>
      <h3>
        Vehicle mix · % <em>live</em>
      </h3>
      {CLASS_KEYS.map((k) => (
        <label key={k} className="ed-row">
          <span>{LABEL[k]}</span>
          <input
            inputMode="decimal"
            aria-invalid={check.error !== null}
            value={text[k]}
            onChange={(e) => setText({ ...text, [k]: e.target.value })}
          />
        </label>
      ))}
      <p className={check.error ? 'ed-error' : 'hint'} role="status">
        {check.error ?? `sum ${check.total} ✓`}
      </p>
      {errors.map((e) => (
        <p key={e.path + e.message} className="ed-error">
          {e.path}: {e.message}
        </p>
      ))}
      <button
        type="button"
        disabled={disabled || !changed}
        onClick={() => check.mix && onApply(check.mix)}
      >
        Apply mix
      </button>
      <p className="hint">
        Applies to vehicles generated from now on. Signal plans keep their design saturation flows
        from the mix at reset; they do not follow live mix changes.
      </p>
    </section>
  );
}
