/** Stored validation results (mirrors backend/tools/validation_measure.py, server/validation_doc.py). */
export interface ValidationItem {
  id: string;
  title: string;
  what: string;
  kind?: 'documented';
  headline?: {
    label: string;
    unit: string;
    measured: string;
    reference: string;
    verdict: string;
  };
  table?: { columns: string[]; rows: (string | number | null)[][] };
  bullets?: string[];
  notes?: string[];
  reference: { text: string; source: string };
  commands: string[];
}

export interface ValidationDoc {
  stamp: { source_digest: string; format_version: number };
  stale: boolean;
  items: ValidationItem[];
}
