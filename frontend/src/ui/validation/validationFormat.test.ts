import { describe, expect, it } from 'vitest';
import { verdictClass } from './validationFormat';

describe('verdictClass', () => {
  it('marks agreement, and shows every stated difference as a difference', () => {
    expect(verdictClass('agrees')).toBe('val-ok');
    expect(verdictClass('68% of HCM')).toBe('val-diff');
    expect(verdictClass('-14% against HCM')).toBe('val-diff');
  });
});
