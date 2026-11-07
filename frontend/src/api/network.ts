import type { NetworkData } from './types';

export async function fetchNetwork(j2MinorLanes = 2, signal?: AbortSignal): Promise<NetworkData> {
  const r = await fetch(`/api/network?j2_minor_lanes=${j2MinorLanes}`, {
    signal,
  });
  if (!r.ok) throw new Error(`GET /api/network failed: ${r.status}`);
  return (await r.json()) as NetworkData;
}
