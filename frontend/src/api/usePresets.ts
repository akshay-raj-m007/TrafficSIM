import { useEffect, useState } from 'react';
import type { PresetInfo } from '../ui/editor/SeedBar';

/** The named scenario presets served by the backend (empty until loaded). */
export function usePresets(): Record<string, PresetInfo> {
  const [presets, setPresets] = useState<Record<string, PresetInfo>>({});
  useEffect(() => {
    fetch('/api/presets')
      .then((r) => r.json() as Promise<Record<string, PresetInfo>>)
      .then(setPresets)
      .catch(() => setPresets({}));
  }, []);
  return presets;
}
