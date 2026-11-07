import type {
  ApiErrors,
  CompareRequest,
  ExperimentDoc,
  ExperimentInfo,
  Job,
  Limits,
} from './compareTypes';
import type { Problem } from './scenarioTypes';

/** A rejected request: the server's per-field messages (HTTP 422 / 429). */
export class RejectedError extends Error {
  constructor(readonly errors: Problem[]) {
    super(errors.map((e) => `${e.path}: ${e.message}`).join('; '));
  }
}

async function json<T>(r: Response): Promise<T> {
  if (r.status === 422 || r.status === 429) {
    throw new RejectedError(((await r.json()) as ApiErrors).errors);
  }
  if (!r.ok) throw new Error(`${r.url} failed: ${r.status}`);
  return (await r.json()) as T;
}

export const fetchLimits = (): Promise<Limits> =>
  fetch('/api/compare/limits').then((r) => json<Limits>(r));
export const fetchExperiments = (): Promise<ExperimentInfo[]> =>
  fetch('/api/experiments').then((r) => json<ExperimentInfo[]>(r));
export const fetchExperiment = (id: string): Promise<ExperimentDoc> =>
  fetch(`/api/experiments/${id}`).then((r) => json<ExperimentDoc>(r));

export const startCompare = (req: CompareRequest): Promise<Job> =>
  fetch('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }).then((r) => json<Job>(r));

export const pollCompare = (id: string): Promise<Job> =>
  fetch(`/api/compare/${id}`).then((r) => json<Job>(r));
export const cancelCompare = (id: string): Promise<unknown> =>
  fetch(`/api/compare/${id}`, { method: 'DELETE' });
