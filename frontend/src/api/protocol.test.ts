import { describe, expect, it } from 'vitest';
import { formatClock, parseServerMessage, wsUrl } from './protocol';

describe('parseServerMessage', () => {
  it('accepts a valid tick frame', () => {
    const raw = '{"type":"tick","tick":12,"t":1.2,"speed":1,"done":false,"step_ms":0.01,"lag_ms":0}';
    expect(parseServerMessage(raw)).toMatchObject({ type: 'tick', tick: 12, t: 1.2 });
  });

  it('accepts busy, pong, hello and error', () => {
    expect(parseServerMessage('{"type":"busy","sessions_max":2,"message":"Server busy"}')?.type).toBe(
      'busy',
    );
    expect(parseServerMessage('{"type":"pong","id":3}')?.type).toBe('pong');
    expect(
      parseServerMessage('{"type":"hello","session_id":"s1","dt":0.1,"speeds":[0,1],"seed":1}')
        ?.type,
    ).toBe('hello');
    expect(parseServerMessage('{"type":"error","message":"bad"}')?.type).toBe('error');
  });

  it('rejects malformed input', () => {
    expect(parseServerMessage('not json')).toBeNull();
    expect(parseServerMessage('null')).toBeNull();
    expect(parseServerMessage('{"type":"tick","tick":"12"}')).toBeNull();
    expect(parseServerMessage('{"type":"unknown"}')).toBeNull();
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
