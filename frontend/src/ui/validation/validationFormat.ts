/** CSS class of a verdict: "agrees" is good; a stated difference is shown as such, not hidden. */
export function verdictClass(verdict: string): 'val-ok' | 'val-diff' {
  return verdict === 'agrees' ? 'val-ok' : 'val-diff';
}
