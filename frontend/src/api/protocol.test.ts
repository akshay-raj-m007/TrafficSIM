import { describe, expect, it } from 'vitest';
import { formatClock, parseServerMessage, wsUrl } from './protocol';

const HELLO =
  '{"type":"hello","session_id":"s1","dt":0.1,"speeds":[0,1],"classes":[],"frame":{"x0_m":0}}';

describe('parseServerMessage', () => {
  it('accepts hello, kpi and stats', () => {
    expect(parseServerMessage(HELLO)?.type).toBe('hello');
    expect(parseServerMessage('{"type":"kpi","t":1.5,"counts":{},"flow":[]}')?.type).toBe('kpi');
    expect(
      parseServerMessage('{"type":"stats","t":1,"tick":10,"speed":1,"done":false,"frames":3}')
        ?.type,
    ).toBe('stats');
  });

  it('accepts busy, pong and error', () => {
    expect(
      parseServerMessage('{"type":"busy","sessions_max":2,"message":"Server busy"}')?.type,
    ).toBe('busy');
    expect(parseServerMessage('{"type":"pong","id":3}')?.type).toBe('pong');
    expect(parseServerMessage('{"type":"error","message":"bad"}')?.type).toBe('error');
  });

  it('rejects malformed input and the retired tick message', () => {
    expect(parseServerMessage('not json')).toBeNull();
    expect(parseServerMessage('null')).toBeNull();
    expect(parseServerMessage('{"type":"hello","session_id":"s1"}')).toBeNull();
    expect(parseServerMessage('{"type":"stats","tick":"12"}')).toBeNull();
    expect(
      parseServerMessage('{"type":"tick","tick":1,"t":0.1,"speed":1,"done":false}'),
    ).toBeNull();
  });
});

describe('formatClock', () => {
  it('formats from integer ticks exactly', () => {
    expect(formatClock(0)).toBe('00:00:00.0');
    expect(formatClock(3)).toBe('00:00:00.3');
    expect(formatClock(36000)).toBe('01:00:00.0');
    expect(formatClock(36000 + 600 + 15)).toBe('01:01:01.5');
  });
});

describe('wsUrl', () => {
  it('uses wss on https and keeps the host', () => {
    expect(wsUrl('/ws/sim', { protocol: 'https:', host: 'x.onrender.com' })).toBe(
      'wss://x.onrender.com/ws/sim',
    );
    expect(wsUrl('/ws/sim', { protocol: 'http:', host: 'localhost:5173' })).toBe(
      'ws://localhost:5173/ws/sim',
    );
  });
});
