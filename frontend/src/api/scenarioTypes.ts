/** Scenario document types (mirrors backend/trafficsim/server/scenario_doc.py). */
export const ZONES = ['W', 'E', 'N1', 'S1', 'N2'] as const;
export type Zone = (typeof ZONES)[number];
export const CLASS_KEYS = ['car', 'truck_bus', 'two_wheeler', 'cav'] as const;
export type ClassKey = (typeof CLASS_KEYS)[number];
export type Policy = 'fixed_webster' | 'max_pressure' | 'max_pressure_threshold';

export interface DemandRow {
  origin: Zone;
  destination: Zone;
  veh_per_h: number;
}
export type Mix = Record<ClassKey, number>; // percent
export type LiveChange =
  | { type: 'set_demand'; demand: DemandRow[] }
  | { type: 'set_mix'; mix: Mix }
  | { type: 'set_policy'; policy: Policy }
  | { type: 'set_flyover'; open: boolean };
export type LoggedChange = LiveChange & { tick: number };

/** Lane groups and widths (applies on reset); mirrors backend network/structure.py. */
export interface StructureDoc {
  j2_minor_lanes: 1 | 2;
  surface_lanes: number;
  flyover_lanes: number;
  surface_width_m: number;
  flyover_width_m: number;
}

export interface ScenarioDoc {
  version: 1;
  name: string;
  seed: number;
  duration_s: number;
  structure: StructureDoc;
  initial: {
    demand: DemandRow[];
    mix: Mix;
    policy: Policy;
    flyover_open: boolean;
  };
  changes: LoggedChange[];
}
export interface Problem {
  path: string;
  message: string;
}
