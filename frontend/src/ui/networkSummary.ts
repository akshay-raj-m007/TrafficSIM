import type { NetworkData } from '../api/types';

export interface NetworkSummary {
  roads: number;
  lanes: number;
  laneKm: number;
  laneCounts: number[];
  laneWidths: number[];
  junctions: { id: string; control: string; movements: number }[];
  flyoverLengthM: number;
  deckZ: number;
}

/** Facts computed directly from the served geometry (nothing hard-coded). */
export function summarise(net: NetworkData): NetworkSummary {
  const lanes = net.roads.flatMap((r) => r.lanes);
  const flyover = net.roads.filter((r) => r.kind === 'flyover');
  return {
    roads: net.roads.length,
    lanes: lanes.length,
    laneKm: lanes.reduce((s, l) => s + l.length_m, 0) / 1000,
    laneCounts: [...new Set(net.roads.map((r) => r.lanes.length))].sort((a, b) => a - b),
    laneWidths: [...new Set(lanes.map((l) => l.width_m))].sort((a, b) => a - b),
    junctions: net.junctions.map((j) => ({
      id: j.id,
      control: j.control.replace('_', '-'),
      movements: net.connectors.filter((c) => c.junction_id === j.id).length,
    })),
    flyoverLengthM: flyover.length ? Math.max(...flyover.map((r) => r.lanes[0]!.length_m)) : 0,
    deckZ: net.meta.deck_z_m,
  };
}
