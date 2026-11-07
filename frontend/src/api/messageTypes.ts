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
  | ScenarioMsg;
