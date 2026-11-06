import { describe, expect, it } from 'vitest';
import { simToThree } from './coords';
import { basisOf, writeBoxMatrix } from './instanceMatrix';
import { SPEED_COLOUR_MAX_KMH, speedColour } from './speedColor';

const det3 = (b: ReturnType<typeof basisOf>) =>
  b.fx * (b.uy * b.rz - b.uz * b.ry) -
  b.fy * (b.ux * b.rz - b.uz * b.rx) +
  b.fz * (b.ux * b.ry - b.uy * b.rx);

describe('vehicle basis in Three.js axes', () => {
  it('heading east: forward +x, up +y, right (south) +z', () => {
    const b = basisOf(0, 0);
    expect([b.fx, b.fy, b.fz]).toEqual([1, 0, -0]);
    expect([b.ux, b.uy]).toEqual([-0, 1]);
    expect([b.rx, b.ry, b.rz]).toEqual([0, 0, 1]);
  });

  it('heading north points to -z (sim north = three -z) and right is east', () => {
    const b = basisOf(Math.PI / 2, 0);
    expect(b.fx).toBeCloseTo(0, 12);
    expect(b.fz).toBeCloseTo(-1, 12);
    expect(b.rx).toBeCloseTo(1, 12);
    expect(b.rz).toBeCloseTo(0, 12);
  });

  it('climbing (pitch > 0) lifts the nose and tilts up backwards', () => {
    const b = basisOf(0, 0.054);
    expect(b.fy).toBeCloseTo(Math.sin(0.054), 12);
    expect(b.ux).toBeLessThan(0); // up leans back, away from the direction of travel
  });

  it('is a right-handed orthonormal frame for any heading and pitch', () => {
    for (const h of [0, 1, 2.5, 4, 6]) {
      for (const p of [-0.1, 0, 0.054]) {
        const b = basisOf(h, p);
        expect(det3(b)).toBeCloseTo(1, 12);
        expect(b.fx ** 2 + b.fy ** 2 + b.fz ** 2).toBeCloseTo(1, 12);
        expect(b.fx * b.ux + b.fy * b.uy + b.fz * b.uz).toBeCloseTo(0, 12);
      }
    }
  });
});

describe('box instance matrices (1 unit = 1 metre)', () => {
  it('places the box half its height above the road surface point, no scaling of positions', () => {
    const out = new Float32Array(32);
    writeBoxMatrix(out, 1, { x: 10, y: 20, z: 6.5 }, 0, 0, { sx: 1, sy: 1, sz: 1 }, { up: 0.75, fwd: 0 });
    const [x, y, z] = simToThree([10, 20, 6.5 + 0.75]);
    expect(Array.from(out.slice(28, 31))).toEqual([x, y, z].map((v) => Math.fround(v)));
    expect(out[31]).toBe(1);
  });

  it('scales a unit box to the lamp size and offsets it behind the vehicle', () => {
    const out = new Float32Array(16);
    writeBoxMatrix(out, 0, { x: 0, y: 0, z: 0 }, 0, 0, { sx: 0.08, sy: 0.14, sz: 1.4 }, { up: 0.8, fwd: -2.25 });
    expect(out[0]).toBeCloseTo(0.08, 6); // length along forward
    expect(out[5]).toBeCloseTo(0.14, 6); // height along up
    expect(out[10]).toBeCloseTo(1.4, 6); // width along right
    expect(out[12]).toBeCloseTo(-2.25, 6); // rear of a 4.5 m car
    expect(out[13]).toBeCloseTo(0.8, 6);
  });

  it('carries the ramp pitch into the box orientation', () => {
    const out = new Float32Array(16);
    writeBoxMatrix(out, 0, { x: 0, y: 0, z: 3 }, 0, 0.054, { sx: 1, sy: 1, sz: 1 });
    expect(out[1]).toBeCloseTo(Math.sin(0.054), 6); // forward axis y component
  });
});

describe('speed colour ramp', () => {
  it('is red when stopped, amber at 30 km/h, cyan at the top and clamps above', () => {
    const [r0, , b0] = speedColour(0);
    expect(r0).toBeGreaterThan(0.9);
    expect(b0).toBeLessThan(0.5);
    const mid = speedColour(30 / 3.6);
    expect(mid[0]).toBeGreaterThan(0.9);
    expect(mid[1]).toBeGreaterThan(0.7);
    const top = speedColour(SPEED_COLOUR_MAX_KMH / 3.6);
    expect(top[2]).toBeGreaterThan(0.8);
    expect(speedColour(100)).toEqual(top);
    expect(speedColour(-3)).toEqual(speedColour(0));
  });
});
