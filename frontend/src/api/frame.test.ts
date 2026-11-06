import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { decodeFrame, NO_SIGNAL } from './frame';
import type { FrameFormat } from './types';

/** The Python encoder wrote these files (backend/tools/gen_golden_frame.py). */
const dir = new URL('./fixtures/', import.meta.url);
const bin = readFileSync(new URL('golden_frame.bin', dir));
const buf = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength) as ArrayBuffer;
const golden = JSON.parse(readFileSync(new URL('golden_frame.json', dir), 'utf-8')) as {
  format: FrameFormat;
  expected: {
    header: Record<string, number>;
    vehicles: Record<string, number[] | boolean[]>;
  };
};

describe('golden frame written by the Python encoder', () => {
  const f = decodeFrame(buf, golden.format);
  const v = golden.expected.vehicles as Record<string, number[]>;

  it('has the header fields the encoder wrote', () => {
    expect(f.n).toBe(golden.expected.header.n);
    expect(f.tick).toBe(123456);
    expect(f.epoch).toBe(7);
    expect(f.phase).toBe(2);
    expect(f.state).toBe(1);
    expect(f.speedIndex).toBe(3);
    expect(buf.byteLength).toBe(golden.format.header_bytes + golden.format.bytes_per_vehicle * f.n);
  });

  it('decodes ids, positions, heading, pitch, speed, brake and class identically', () => {
    // Float32 holds 1500 m to ~1e-4 m; the Python reference is float64.
    const close = (a: ArrayLike<number>, b: number[], tol: number) =>
      b.forEach((x, i) => expect(Math.abs(a[i]! - x)).toBeLessThanOrEqual(tol));
    expect(Array.from(f.id)).toEqual(v.id);
    close(f.x, v.x!, 2e-4);
    close(f.y, v.y!, 2e-4);
    close(f.z, v.z!, 2e-4);
    close(f.heading, v.heading!, 1e-5);
    close(f.pitch, v.pitch!, 1e-6);
    close(f.speed, v.speed!, 1e-5);
    expect(Array.from(f.brake).map(Boolean)).toEqual(golden.expected.vehicles.brake);
    expect(Array.from(f.cls)).toEqual(v.cls);
  });

  it('wraps ids to 16 bits and clamps out-of-range pitch and speed', () => {
    expect(f.id[1]).toBe(1); // 65537 & 0xFFFF
    expect(f.pitch[4]).toBeCloseTo(0.127, 6);
    expect(f.speed[4]).toBeCloseTo(25.5, 5);
  });
});

describe('malformed frames', () => {
  it('rejects wrong type and wrong size', () => {
    const fmt = golden.format;
    expect(() => decodeFrame(buf.slice(0, buf.byteLength - 1), fmt)).toThrow();
    const bad = buf.slice(0);
    new Uint8Array(bad)[0] = 2;
    expect(() => decodeFrame(bad, fmt)).toThrow();
  });

  it('decodes an empty frame', () => {
    const fmt = golden.format;
    const empty = new ArrayBuffer(fmt.header_bytes);
    const view = new DataView(empty);
    view.setUint8(0, 1);
    view.setUint8(1, NO_SIGNAL);
    const f = decodeFrame(empty, fmt);
    expect(f.n).toBe(0);
    expect(f.phase).toBe(NO_SIGNAL);
  });
});
