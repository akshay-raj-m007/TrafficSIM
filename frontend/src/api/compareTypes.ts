/** A/B comparison API types (mirrors backend/trafficsim/server/compare_*.py). */
import type { Problem, ScenarioDoc } from './scenarioTypes';

export interface PerSeed {
  a: number | null;
  b: number | null;
}

export interface MetricRow {
  id: string;
  label: string;
  unit: string;
  n: number; // pairs used (undefined pairs are dropped from this metric only)
  mean_a: number | null;
  mean_b: number | null;
  diff: number | null; // B - A
  ci_lo: number | null;
  ci_hi: number | null;
  df: number | null;
  t_crit: number | null;
  p: number | null;
  significant: boolean | null;
  identical: boolean | null;
  constant_difference?: boolean; // every seed shows the same non-zero difference
  per_seed: PerSeed[];
}

export interface SideInfo {
  name: string;
  demand_veh_h: number;
  j2_minor_lanes: number;
  policy: string;
  flyover_open: boolean;
  changes: number;
}

export interface Counts {
  cohort: number;
  completed: number;
  unfinished: number;
  too_young: number;
}

export interface Cost {
  cpu_s: number; // computed by this request
  run_cpu_s: number; // CPU time the runs of this comparison took in total (also if cached)
  wall_s: number;
  workers: number;
  cached_runs: number;
  computed_runs: number;
}

export interface ComparisonResult {
  meta: {
    runs: number;
    seeds: number[];
    duration_s: number;
    warmup_s: number;
    base_seed: number;
    a: SideInfo;
    b: SideInfo;
    paired_arrivals: boolean;
    pairing_note: string | null;
    mean_counts: { a: Counts; b: Counts };
    cost: Cost;
  };
  metrics: MetricRow[];
  note: string;
}

export interface CompareRequest {
  a: ScenarioDoc;
  b: ScenarioDoc;
  runs: number;
  duration_s: number;
  warmup_s: number;
  base_seed: number;
}

export interface Job {
  id: string;
  state: 'running' | 'stopping' | 'done' | 'error' | 'cancelled';
  phase: 'preparing' | 'running';
  total: number;
  done: number;
  cached: number;
  error: string | null;
  result: ComparisonResult | null;
  elapsed_s: number;
}

export interface Limits {
  runs: number[];
  max_duration_s: number;
  max_jobs: number;
  default_duration_s: number;
  default_warmup_s: number;
}

export interface ExperimentInfo {
  id: string;
  title: string;
  description: string;
  available: boolean;
  stale: boolean | null;
  comparisons: string[];
  params: { runs: number; duration_s: number; warmup_s: number; base_seed: number };
}

export interface ExperimentDoc {
  id: string;
  title: string;
  description: string;
  stale: boolean;
  comparisons: { label: string; result: ComparisonResult }[];
}

export type ApiErrors = { errors: Problem[] };
