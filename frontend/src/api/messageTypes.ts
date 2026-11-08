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
/** The server paused the session after minutes without activity and closed it. */
export interface IdleMsg {
  type: 'idle';
  message: string;
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
  /** Set when this layout's tables must be measured first: about this many seconds. */
  estimate_s?: number | null;
  done?: number; // measurement steps done / in total
  total?: number;
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
/** The inspected vehicle (backend server/inspector.py); `gone` once it has left the network. */
export interface VehicleLiveMsg {
  type: 'vehicle';
  gone: false;
  id: number;
  vid: number;
  t: number;
  class: string;
  idm: {
    length_m: number;
    width_m: number;
    v0_mps: number;
    T_s: number;
    a_mps2: number;
    b_mps2: number;
    s0_m: number;
  };
  mobil: {
    politeness: number;
    threshold_mps2: number;
    keep_left_bias_mps2: number;
    b_safe_mps2: number;
    cooldown_s: number;
  };
  origin: string;
  destination: string;
  route: string[];
  road: string | null;
  lane: string;
  s_m: number;
  speed_mps: number;
  acc_mps2: number;
  t_gen: number;
  t_ins: number;
  free_flow_s: number | null;
  delay_s: number | null;
  lane_changes: number;
}
export interface VehicleGoneMsg {
  type: 'vehicle';
  gone: true;
  id: number;
  t_exit: number | null;
  lane_changes: number;
}
export type VehicleMsg = VehicleLiveMsg | VehicleGoneMsg;
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
  | ChartsMsg
  | IdleMsg
  | VehicleMsg;
