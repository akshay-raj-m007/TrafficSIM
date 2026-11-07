import { useEffect, useState } from 'react';
import { fetchNetwork } from './network';
import type { StructureDoc } from './scenarioTypes';
import type { NetworkData } from './types';

/** The network geometry of a structure, fetched again whenever the structure changes. */
export function useNetwork(structure: StructureDoc): {
  network: NetworkData | null;
  netError: string | null;
} {
  const [network, setNetwork] = useState<NetworkData | null>(null);
  const [netError, setNetError] = useState<string | null>(null);
  const key = JSON.stringify(structure);
  useEffect(() => {
    const ctrl = new AbortController();
    fetchNetwork(JSON.parse(key) as StructureDoc, ctrl.signal)
      .then((n) => {
        setNetwork(n);
        setNetError(null);
      })
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) setNetError(String(e));
      });
    return () => ctrl.abort();
  }, [key]);
  return { network, netError };
}
