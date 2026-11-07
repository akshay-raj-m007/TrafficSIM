/** Mirrors backend/trafficsim/network/serialize.py, server/protocol.py and engine/kpi.py. */
import type { Vec3 } from '../scene/coords';
import type { LoggedChange, Problem, ScenarioDoc } from './scenarioTypes';

export interface LaneData {
  id: string;
  index: number; // 0 = kerb lane (left-hand traffic)
  width_m: number;
  length_m: number;
  centreline: Vec3[]; // sim axes: x east, y north, z up
}

export type RoadKind = 'surface' | 'flyover' | 'ramp';

export interface RoadData {
  id: string;
  kind: RoadKind;
  level: number;
  speed_limit_mps: number;
  reference: Vec3[];
  inner_offset_m: number;
  lanes: LaneData[];
}

export type Movement = 'through' | 'left' | 'right';

export interface ConnectorData {
  id: string;
  from_lane: string;
  to_lane: string;
  movement: Movement;
  junction_id: string | null;
  yields: boolean;
  length_m: number;
  path: Vec3[];
}

export interface JunctionData {
  id: string;
  control: 'signalised' | 'give_way';
  polygon: Vec3[];
  approach_lanes: string[];
  minor_approach_lanes: string[];
}

export interface NetworkData {
  meta: {
    units: 'm';
    drive_side: 'left' | 'right';
    deck_z_m: number;
    deck_thickness_m: number;
    min_clearance_m: number;
    median_half_m: number;
  };
  roads: RoadData[];
  connectors: ConnectorData[];
  junctions: JunctionData[];
  zones: { id: string; entry_road: string; exit_road: string }[];
  annotations: { text: string; position: Vec3; kind: string }[];
}

// ---- WebSocket protocol -------------------------------------------------------------
export interface FrameFormat {
  s_scale_m: number;
  lat_scale_m: number;
  speed_scale_mps: number;
  header_bytes: number;
  bytes_per_vehicle: number;
}

export interface VehicleClassInfo {
  name: string;
  length_m: number;
  width_m: number;
  height_m: number;
}

/** One lane or junction connector of the compiled lane graph; the index is the frame's id. */
export interface SegmentInfo {
  id: string;
  length_m: number;
  next: number[]; // successor segment indices
}

export interface HelloMsg {
  type: 'hello';
  session_id: string;
  dt: number;
  steps_per_second: number;
  tick_hz: number;
  speeds: number[];
  seed: number;
  signal: string;
  demand_scale: number;
  duration_s: number;
  epoch: number;
  classes: VehicleClassInfo[];
  frame: FrameFormat;
  segments: SegmentInfo[];
  scenario: ScenarioDoc | null; // the document in force (null for experiment-only setups)
  network: { j2_minor_lanes: 1 | 2 };
  lane_change_blend_s: number;
  kpi_defs: Record<string, string>;
}

export interface FlowKpi {
  id: string;
  label: string;
  veh_per_h: number;
  in_window: number;
  total: number;
}
export interface QueueKpi {
  id: string;
  label: string;
  veh: number;
  length_m: number;
  max_window_m: number;
}
export interface SignalKpi {
  junction: string;
  controller: string;
  phase: number;
  approach: string;
  state: 'green' | 'amber' | 'all_red';
  elapsed_s: number;
  n_phases: number;
  cycle_s?: number;
}
export interface DelayKpi {
  reference_ready: boolean;
  n: number;
  mean_s: number | null;
  recent_n: number;
  recent_mean_s: number | null;
  entry_wait_mean_s: number | null;
}
export interface KpiMsg {
  type: 'kpi';
  t: number;
  tick: number;
  counts: {
    generated: number;
    inserted: number;
    exited: number;
    active: number;
    queued: number;
  };
  signal: SignalKpi | null;
  flow: FlowKpi[];
  queues: QueueKpi[];
  delay: DelayKpi;
  unserved: {
    queued: number;
    oldest_wait_s: number;
    by_zone: Record<string, number>;
  };
}

export interface StatsMsg {
  type: 'stats';
  t: number;
  tick: number;
  speed: number;
  done: boolean;
  lag_ms: number;
  frames: number;
  frame_bytes_mean: number;
  bytes_per_s: number;
  step_ms_mean: number;
  step_ms_max: number;
  encode_ms_mean: number;
  bytes_total: number;
  frames_total: number;
  vehicles: number;
}

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
export interface AppliedMsg {
  type: 'applied';
  tick: number;
  change: LoggedChange;
}
export interface RejectedMsg {
  type: 'rejected';
  request: 'apply' | 'reset' | 'export';
  errors: Problem[];
}
export interface ScenarioMsg {
  type: 'scenario';
  scenario: ScenarioDoc;
}
export type ServerMsg =
  | HelloMsg
  | KpiMsg
  | StatsMsg
  | BusyMsg
  | PongMsg
  | ErrorMsg
  | AppliedMsg
  | RejectedMsg
  | ScenarioMsg;
