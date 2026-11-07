import type { StructureDoc } from './scenarioTypes';
import type { NetworkData } from './types';

export async function fetchNetwork(
  structure: StructureDoc,
  signal?: AbortSignal,
): Promise<NetworkData> {
  const query = new URLSearchParams(Object.entries(structure).map(([k, v]) => [k, String(v)]));
  const r = await fetch(`/api/network?${query.toString()}`, { signal });
  if (!r.ok) throw new Error(`GET /api/network failed: ${r.status}`);
  return (await r.json()) as NetworkData;
}
