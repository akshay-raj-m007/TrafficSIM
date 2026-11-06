import type { NetworkData } from './types';

export async function fetchNetwork(signal?: AbortSignal): Promise<NetworkData> {
  const r = await fetch('/api/network', { signal });
  if (!r.ok) throw new Error(`GET /api/network failed: ${r.status}`);
  return (await r.json()) as NetworkData;
}
