import type { ScenarioDoc } from '../api/scenarioTypes';

/** Save a scenario document as a JSON file in the browser. */
export function downloadJson(doc: ScenarioDoc): void {
  const blob = new Blob([JSON.stringify(doc, null, 2)], {
    type: 'application/json',
  });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `scenario-${doc.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-seed${doc.seed}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}
