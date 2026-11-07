/**
 * Smooth vehicle motion between server frames, independent of the display frame rate.
 *
 * The server sends a frame each time the simulation advanced (10 Hz at speeds ≥ 1×; one
 * frame per 400 ms at 0.25×). The renderer keeps a *render clock measured in simulation
 * ticks*: it advances at `speed × ticksPerSecond` of wall time and is held
 * INTERP_DELAY_FRAMES frame intervals behind the newest frame, so there are always two
 * frames to interpolate between and a frame may arrive up to one whole interval late
 * without a stall. Interpolation is linear in position, pitch and speed and takes the
 * shortest way round for heading. Vehicles are matched by id.
 *
 * With a `LanePlacer` a vehicle moves along the lane graph between two frames (lane ->
 * junction connector -> lane), so turns follow the curve even at 5-10× where consecutive
 * frames are 0.5-1 s of simulated time apart. If the two positions are not connected (a
 * lane change) the two world poses are interpolated, which is a short lateral move.
 */
import type { Frame } from '../api/frame';
import type { LanePlacer, Pose } from './laneGeometry';

export const INTERP_DELAY_FRAMES = 2;
const MAX_BUFFERED_FRAMES = 16;
const MAX_DT_S = 0.25; // wall-clock gap treated as a hiccup (tab asleep): no big jump
const TWO_PI = 2 * Math.PI;

export interface RenderState {
  n: number;
  tick: number; // fractional render tick
  id: Uint16Array;
  x: Float32Array;
  y: Float32Array;
  z: Float32Array;
  heading: Float32Array;
  pitch: Float32Array;
  speed: Float32Array;
  brake: Uint8Array;
  cls: Uint8Array;
}

function emptyState(capacity: number): RenderState {
  return {
    n: 0,
    tick: 0,
    id: new Uint16Array(capacity),
    x: new Float32Array(capacity),
    y: new Float32Array(capacity),
    z: new Float32Array(capacity),
    heading: new Float32Array(capacity),
    pitch: new Float32Array(capacity),
    speed: new Float32Array(capacity),
    brake: new Uint8Array(capacity),
    cls: new Uint8Array(capacity),
  };
}

export function shortestAngleDelta(from: number, to: number): number {
  const d = to - from;
  return d - TWO_PI * Math.round(d / TWO_PI);
}

export class FrameInterpolator {
  private frames: Frame[] = [];
  private renderTick: number | null = null;
  private lastNowMs: number | null = null;
  private pairKey = -1;
  private lastDelta = 1; // ticks between the last two frames
  private bIndex = new Map<number, number>();
  private out = emptyState(1024);
  private readonly pose: Pose = { x: 0, y: 0, z: 0, heading: 0, pitch: 0 };

  /** `speeds[i]` is the simulated-seconds-per-second of the frame header's speed index i. */
  constructor(
    private readonly ticksPerSecond: number,
    private readonly speeds: readonly number[],
    private readonly placer?: LanePlacer,
  ) {}

  reset(): void {
    this.frames = [];
    this.renderTick = null;
    this.lastNowMs = null;
    this.pairKey = -1;
    this.lastDelta = 1;
  }

  push(frame: Frame): void {
    const last = this.frames[this.frames.length - 1];
    if (last && (frame.epoch !== last.epoch || frame.tick < last.tick)) this.reset();
    else if (last && frame.tick === last.tick) {
      this.frames[this.frames.length - 1] = frame; // same state again: keep the newest copy
      return;
    }
    this.frames.push(frame);
    if (this.frames.length > MAX_BUFFERED_FRAMES) this.frames.shift();
  }

  get latest(): Frame | null {
    return this.frames[this.frames.length - 1] ?? null;
  }

  /** Advance the render clock to `nowMs` and return the interpolated vehicles. */
  sample(nowMs: number): RenderState | null {
    const frames = this.frames;
    const newest = frames[frames.length - 1];
    if (!newest) return null;
    const dt = this.lastNowMs === null ? 0 : Math.min((nowMs - this.lastNowMs) / 1000, MAX_DT_S);
    this.lastNowMs = nowMs;

    if (frames.length >= 2) {
      this.lastDelta = Math.max(1, newest.tick - frames[frames.length - 2]!.tick);
    }
    const delta = this.lastDelta;
    const speed = this.speeds[newest.speedIndex] ?? 1;
    let t = this.renderTick ?? Math.max(frames[0]!.tick, newest.tick - INTERP_DELAY_FRAMES * delta);
    // Paused: keep moving at 1x until the render clock reaches the last simulated tick.
    t += dt * (speed === 0 ? 1 : speed) * this.ticksPerSecond;
    t = Math.max(t, newest.tick - (INTERP_DELAY_FRAMES + 1) * delta); // too far behind: catch up
    t = Math.min(t, newest.tick); // never run ahead of what the server has sent
    t = Math.max(t, frames[0]!.tick);
    this.renderTick = t;

    let ai = 0;
    while (ai + 1 < frames.length && frames[ai + 1]!.tick <= t) ai++;
    if (ai > 0) frames.splice(0, ai);
    const a = frames[0]!;
    const b = frames[1];
    return b ? this.blend(a, b, (t - a.tick) / (b.tick - a.tick), t) : this.copy(a, t);
  }

  private ensureCapacity(n: number): void {
    if (n > this.out.id.length) this.out = emptyState(Math.max(n, this.out.id.length * 2));
  }

  private copy(a: Frame, t: number): RenderState {
    this.ensureCapacity(a.n);
    const o = this.out;
    o.n = a.n;
    o.tick = t;
    o.id.set(a.id);
    o.x.set(a.x);
    o.y.set(a.y);
    o.z.set(a.z);
    o.heading.set(a.heading);
    o.pitch.set(a.pitch);
    o.speed.set(a.speed);
    o.brake.set(a.brake);
    o.cls.set(a.cls);
    return o;
  }

  private blend(a: Frame, b: Frame, u: number, t: number): RenderState {
    if (this.pairKey !== a.tick * 1e7 + b.tick) {
      this.pairKey = a.tick * 1e7 + b.tick;
      this.bIndex = new Map();
      for (let j = 0; j < b.n; j++) this.bIndex.set(b.id[j]!, j);
    }
    this.ensureCapacity(a.n);
    const o = this.out;
    o.n = a.n;
    o.tick = t;
    for (let i = 0; i < a.n; i++) {
      const j = this.bIndex.get(a.id[i]!);
      o.id[i] = a.id[i]!;
      o.cls[i] = a.cls[i]!;
      if (j === undefined) {
        // leaves the network before b: hold its last position until the pair advances
        o.x[i] = a.x[i]!;
        o.y[i] = a.y[i]!;
        o.z[i] = a.z[i]!;
        o.heading[i] = a.heading[i]!;
        o.pitch[i] = a.pitch[i]!;
        o.speed[i] = a.speed[i]!;
        o.brake[i] = a.brake[i]!;
        continue;
      }
      const lat = a.lat[i]! + (b.lat[j]! - a.lat[i]!) * u;
      const p = this.pose;
      if (this.placer?.between(a.seg[i]!, a.s[i]!, b.seg[j]!, b.s[j]!, lat, u, p)) {
        o.x[i] = p.x;
        o.y[i] = p.y;
        o.z[i] = p.z;
        o.heading[i] = p.heading;
        o.pitch[i] = p.pitch;
      } else {
        o.x[i] = a.x[i]! + (b.x[j]! - a.x[i]!) * u;
        o.y[i] = a.y[i]! + (b.y[j]! - a.y[i]!) * u;
        o.z[i] = a.z[i]! + (b.z[j]! - a.z[i]!) * u;
        o.heading[i] = a.heading[i]! + shortestAngleDelta(a.heading[i]!, b.heading[j]!) * u;
        o.pitch[i] = a.pitch[i]! + (b.pitch[j]! - a.pitch[i]!) * u;
      }
      o.speed[i] = a.speed[i]! + (b.speed[j]! - a.speed[i]!) * u;
      o.brake[i] = u < 0.5 ? a.brake[i]! : b.brake[j]!;
    }
    return o;
  }
}
