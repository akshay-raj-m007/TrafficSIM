import type { ServerMsg } from './types';

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isStr = (v: unknown): v is string => typeof v === 'string';

/** Parse and validate one JSON server message; returns null for anything malformed. */
export function parseServerMessage(raw: string): ServerMsg | null {
  let m: unknown;
  try {
    m = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof m !== 'object' || m === null) return null;
  const o = m as Record<string, unknown>;
  switch (o.type) {
    case 'hello':
      return isStr(o.session_id) &&
        isNum(o.dt) &&
        Array.isArray(o.speeds) &&
        Array.isArray(o.classes) &&
        typeof o.frame === 'object' &&
        o.frame !== null
        ? (o as unknown as ServerMsg)
        : null;
    case 'kpi':
      return isNum(o.t) && typeof o.counts === 'object' && Array.isArray(o.flow ?? [])
        ? (o as unknown as ServerMsg)
        : null;
    case 'stats':
      return isNum(o.t) && isNum(o.tick) && isNum(o.speed) && typeof o.done === 'boolean'
        ? (o as unknown as ServerMsg)
        : null;
    case 'busy':
      return isStr(o.message) ? (o as unknown as ServerMsg) : null;
    case 'pong':
      return isNum(o.id) ? (o as unknown as ServerMsg) : null;
    case 'error':
      return isStr(o.message) ? (o as unknown as ServerMsg) : null;
    case 'applied':
      return isNum(o.tick) && typeof o.change === 'object' ? (o as unknown as ServerMsg) : null;
    case 'rejected':
      return isStr(o.request) && Array.isArray(o.errors) ? (o as unknown as ServerMsg) : null;
    case 'scenario':
      return typeof o.scenario === 'object' && o.scenario !== null
        ? (o as unknown as ServerMsg)
        : null;
    default:
      return null;
  }
}

/** Format a sim clock from the integer tick (exact, no float rounding). */
export function formatClock(tick: number, stepsPerSecond = 10): string {
  const tenths = tick % stepsPerSecond;
  const totalS = Math.floor(tick / stepsPerSecond);
  const h = Math.floor(totalS / 3600);
  const m = Math.floor((totalS % 3600) / 60);
  const s = totalS % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}.${tenths}`;
}

/** WebSocket URL on the same origin as the page (works behind the Vite proxy too). */
export function wsUrl(path: string, loc: Pick<Location, 'protocol' | 'host'>): string {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${loc.host}${path}`;
}
