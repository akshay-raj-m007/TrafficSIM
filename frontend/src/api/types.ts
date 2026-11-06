/** Mirrors backend/trafficsim/network/serialize.py and server/protocol.py. */
import type { Vec3 } from '../scene/coords';

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
export interface HelloMsg {
  type: 'hello';
  session_id: string;
  dt: number;
  tick_hz: number;
  speeds: number[];
  seed: number;
  duration_s: number;
}
export interface TickMsg {
  type: 'tick';
  tick: number;
  t: number;
  speed: number;
  done: boolean;
  step_ms: number;
  lag_ms: number;
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
export type ServerMsg = HelloMsg | TickMsg | BusyMsg | PongMsg | ErrorMsg;
