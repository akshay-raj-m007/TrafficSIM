import { describe, expect, it } from 'vitest';
import type { Frame } from '../api/frame';
import { FrameInterpolator, INTERP_DELAY_FRAMES, shortestAngleDelta } from './interpolator';

const SPEEDS = [0, 0.25, 0.5, 1, 2, 5, 10];
const TPS = 10;
const DISPLAY_DT_MS = 1000 / 60;
const V_PER_TICK = 1.4; // metres per tick of the test vehicle (14 m/s at 10 ticks/s)

interface V {
  id: number;
  x: number;
  heading?: number;
}

function frame(tick: number, vs: V[], speedIndex = 3, epoch = 0): Frame {
  const n = vs.length;
  const f = (g: (v: V) => number) => Float32Array.from(vs.map(g));
  return {
    tick, epoch, phase: 255, state: 255, speedIndex, n,
    id: Uint16Array.from(vs.map((v) => v.id)),
    seg: f(() => 0) as unknown as Uint16Array, s: f(() => 0), lat: f(() => 0),
    x: f((v) => v.x), y: f(() => 0), z: f(() => 0),
    heading: f((v) => v.heading ?? 0), pitch: f(() => 0), speed: f(() => 14),
    brake: Uint8Array.from(vs.map(() => 0)), cls: Uint8Array.from(vs.map(() => 0)),
  };
}

/** Run a wall clock at 60 fps; frames arrive every `frameMs` carrying `ticksPerFrame`. */
function run(opts: {
  speedIndex: number;
  frameMs: number;
  ticksPerFrame: number;
  seconds: number;
  skip?: (k: number) => boolean; // drop frame k (late/lost)
}) {
  const it = new FrameInterpolator(TPS, SPEEDS);
  const xs: number[] = [];
  const times: number[] = [];
  let k = 0;
  for (let now = 0; now <= opts.seconds * 1000; now += DISPLAY_DT_MS) {
    while (k * opts.frameMs <= now) {
      if (!opts.skip?.(k)) {
        const tick = k * opts.ticksPerFrame;
        it.push(frame(tick, [{ id: 1, x: V_PER_TICK * tick }], opts.speedIndex));
      }
      k++;
    }
    const s = it.sample(now);
    if (s && s.n) {
      xs.push(s.x[0]!);
      times.push(now);
    }
  }
  return { xs, times, it };
}

/** Advance the wall clock to `toMs` in display-sized steps, like a real render loop. */
function sampleAt(it: FrameInterpolator, fromMs: number, toMs: number) {
  let s = it.sample(fromMs);
  for (let now = fromMs + DISPLAY_DT_MS; now < toMs; now += DISPLAY_DT_MS) s = it.sample(now);
  return it.sample(toMs) ?? s;
}

const steps = (xs: number[]) => xs.slice(1).map((x, i) => x - xs[i]!);

describe('smooth motion at the display frame rate', () => {
  const cases: [string, number, number, number][] = [
    // name, speedIndex, frame interval ms, ticks per frame
    ['1x', 3, 100, 1],
    ['0.25x (one tick per 400 ms)', 1, 400, 1],
    ['0.5x', 2, 200, 1],
    ['2x', 4, 100, 2],
    ['10x (one second of sim per frame)', 6, 100, 10],
  ];
  for (const [name, speedIndex, frameMs, ticksPerFrame] of cases) {
    it(`${name}: per-display-frame displacement is constant (no hitches)`, () => {
      const speed = SPEEDS[speedIndex]!;
      const { xs } = run({ speedIndex, frameMs, ticksPerFrame, seconds: 6 });
      const settled = xs.slice(Math.ceil((4 * frameMs) / DISPLAY_DT_MS)); // after warm-up
      const expected = V_PER_TICK * speed * TPS * (DISPLAY_DT_MS / 1000);
      const d = steps(settled);
      expect(d.length).toBeGreaterThan(60);
      const worst = Math.max(...d.map((x) => Math.abs(x - expected)));
      console.log(`[smoothness ${name}] expected ${expected.toFixed(4)} m/frame, worst deviation ${worst.toExponential(2)} m`);
      expect(worst).toBeLessThan(1e-3);
      expect(Math.min(...d)).toBeGreaterThan(0); // always moving forward
    });
  }
});

describe('render clock', () => {
  it('renders between INTERP_DELAY_FRAMES-1 and INTERP_DELAY_FRAMES intervals behind the newest', () => {
    const it = new FrameInterpolator(TPS, SPEEDS);
    for (let k = 0; k < 10; k++) it.push(frame(k, [{ id: 1, x: V_PER_TICK * k }]));
    // first sample initialises the clock INTERP_DELAY_FRAMES behind the newest frame
    const s = it.sample(0)!;
    expect(s.tick).toBeCloseTo(9 - INTERP_DELAY_FRAMES, 6);
  });

  it('holds on the newest frame when none arrives, then resumes without going backwards', () => {
    const { xs, it } = run({ speedIndex: 3, frameMs: 100, ticksPerFrame: 1, seconds: 8,
      skip: (k) => k >= 30 && k < 38 }); // 0.8 s without frames
    expect(Math.min(...steps(xs))).toBeGreaterThanOrEqual(0);
    expect(it.latest!.tick).toBeGreaterThan(70);
  });

  it('settles on the last simulated tick when paused', () => {
    const it = new FrameInterpolator(TPS, SPEEDS);
    for (let k = 0; k <= 20; k++) it.push(frame(k, [{ id: 1, x: V_PER_TICK * k }], 3));
    it.push(frame(20, [{ id: 1, x: V_PER_TICK * 20 }], 0)); // speed 0: same tick again
    let s = it.sample(0)!;
    for (let now = 16; now <= 4000; now += 16) s = it.sample(now)!;
    expect(s.tick).toBe(20);
    expect(s.x[0]).toBeCloseTo(V_PER_TICK * 20, 4);
  });

  it('clears the buffer when the epoch changes (simulation reset)', () => {
    const it = new FrameInterpolator(TPS, SPEEDS);
    for (let k = 0; k < 30; k++) it.push(frame(k, [{ id: 1, x: V_PER_TICK * k }], 3, 0));
    it.sample(0);
    it.push(frame(0, [{ id: 7, x: 5 }], 3, 1));
    const s = it.sample(16)!;
    expect(s.n).toBe(1);
    expect(s.id[0]).toBe(7);
    expect(s.x[0]).toBeCloseTo(5, 6);
  });

  it('treats a tick that goes backwards as a restart', () => {
    const it = new FrameInterpolator(TPS, SPEEDS);
    it.push(frame(100, [{ id: 1, x: 1 }]));
    it.push(frame(3, [{ id: 2, x: 2 }]));
    expect(it.sample(0)!.id[0]).toBe(2);
  });
});

describe('vehicles that appear and vanish', () => {
  it('holds a leaving vehicle until the pair advances and shows a new one only then', () => {
    const it = new FrameInterpolator(TPS, SPEEDS);
    it.push(frame(0, [{ id: 1, x: 0 }, { id: 2, x: 10 }]));
    it.push(frame(10, [{ id: 2, x: 20 }, { id: 3, x: 5 }]));
    it.push(frame(20, [{ id: 2, x: 30 }, { id: 3, x: 15 }]));
    // initial render tick = newest(20) - 2 * 10 = 0: between frame 0 and frame 10
    let s = it.sample(0)!;
    expect(Array.from(s.id.slice(0, s.n))).toEqual([1, 2]);
    s = sampleAt(it, 0, 500)!; // half way to tick 10 at 1x (5 ticks)
    expect(s.tick).toBeCloseTo(5, 3);
    expect(s.x[0]).toBe(0); // id 1 leaves: held at its last position
    expect(s.x[1]).toBeCloseTo(15, 3); // id 2: 10 -> 20, u = 0.5
    s = sampleAt(it, 500, 1100)!; // past tick 10: pair is now (10, 20)
    expect(Array.from(s.id.slice(0, s.n))).toEqual([2, 3]);
  });
});

describe('heading', () => {
  it('takes the shortest way round 0/2π', () => {
    expect(shortestAngleDelta(6.2, 0.1)).toBeCloseTo(0.1 + (2 * Math.PI - 6.2), 9);
    expect(shortestAngleDelta(0.1, 6.2)).toBeLessThan(0);
    const it = new FrameInterpolator(TPS, SPEEDS);
    it.push(frame(0, [{ id: 1, x: 0, heading: 6.2 }]));
    it.push(frame(10, [{ id: 1, x: 0, heading: 0.1 }]));
    it.push(frame(20, [{ id: 1, x: 0, heading: 0.1 }]));
    const s = sampleAt(it, 0, 500)!; // half way
    const mid = 6.2 + (0.1 + (2 * Math.PI - 6.2)) / 2;
    expect(s.heading[0]).toBeCloseTo(mid, 4);
  });
});
