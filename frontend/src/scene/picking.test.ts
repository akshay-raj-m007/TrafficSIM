import { describe, expect, it } from 'vitest';
import { CLICK_MAX_MS, CLICK_MAX_PX, isClick, toNdc } from './picking';

describe('isClick', () => {
  const down = { x: 100, y: 100, t: 0 };
  it('is a click when the pointer barely moved and was released quickly', () => {
    expect(isClick(down, { x: 102, y: 101, t: 150 })).toBe(true);
  });
  it('is a drag (the camera) when the pointer moved', () => {
    expect(isClick(down, { x: 100 + CLICK_MAX_PX + 1, y: 100, t: 100 })).toBe(false);
  });
  it('is not a click after a long press, or without a press', () => {
    expect(isClick(down, { x: 100, y: 100, t: CLICK_MAX_MS + 1 })).toBe(false);
    expect(isClick(null, { x: 0, y: 0, t: 0 })).toBe(false);
  });
});

describe('toNdc', () => {
  const box = { left: 10, top: 20, width: 200, height: 100 } as DOMRect;
  it('maps the corners and the centre of the canvas box', () => {
    expect(toNdc(10, 20, box).toArray()).toEqual([-1, 1]);
    expect(toNdc(210, 120, box).toArray()).toEqual([1, -1]);
    const c = toNdc(110, 70, box);
    expect(c.x).toBeCloseTo(0);
    expect(c.y).toBeCloseTo(0);
  });
});
