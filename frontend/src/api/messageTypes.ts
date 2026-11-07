/** Server message types of the live session (mirrors backend/trafficsim/server/protocol.py). */
import type { LoggedChange, Problem, ScenarioDoc } from './scenarioTypes';
import type { HelloMsg, KpiMsg, StatsMsg } from './types';

export interface BusyMsg {
  type: 'busy';
  sessions_max: number;
  message: string;
}
export interface PongMsg {
  type: 'pong';
  id: number;
}
export interface ErrorMsg {
  type: 'error';
  message: string;
  detail?: unknown;
}

export interface BuildingMsg {
  type: 'building';
  reason: string;
  name: string;
}
export interface AppliedMsg {
  type: 'applied';
  tick: number;
  change: LoggedChange;
}
export interface RejectedMsg {
  type: 'rejected';
  request: 'apply' | 'reset' | 'export' | 'message';
  errors: Problem[];
}
export interface ScenarioMsg {
  type: 'scenario';
  scenario: ScenarioDoc;
}
export interface ChartCorridor {
  key: string;
  label: string;
  cells: number;
  length_m: number;
  marks: { id: string; x_m: number }[];
}
/** What the chart meters measured since the last message (backend engine/charts.py). */
export interface ChartsMsg {
  type: 'charts';
  col0: number; // absolute index of the first speed column
  cell_m: number;
  corridors: ChartCorridor[];
  speed_unit_mps: number;
  no_data: number;
  cols: string[]; // one base64 string per second: the cells of all corridors, back to back
  mfd: [number, number, number, boolean][]; // t [s], density [veh/km/lane], flow [veh/h/lane], flyover open
  queue: [number, number, number][]; // t [s], J1 and J2 longest queue [m]
}
export type ServerMsg =
  | HelloMsg
  | KpiMsg
  | StatsMsg
  | BusyMsg
  | PongMsg
  | ErrorMsg
  | AppliedMsg
  | BuildingMsg
  | RejectedMsg
  | ScenarioMsg
  | ChartsMsg;
