// Mirror of the API's job envelope (backend/app/api/schema/job.py and
// docs/schema.md). Kept deliberately small — just what the UI renders.

export type JobStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface BillingRecord {
  treatment_date: string;
  cpt_codes: string[];
  description: string | null;
  provider: string;
  insurers: string[];
  third_parties: string[];
  total_charges: number | null;
  ins_paid: number | null;
  adjustment: number | null;
  payments: number | null;
  balance: number | null;
  page: string;
}

export interface FlaggedRecord {
  row: number | null;
  fields: string[];
  reason: string;
  page: string;
  severity: "low" | "medium" | "high";
}

export interface TokenUsage {
  input: number;
  output: number;
  total: number;
  [key: string]: number;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  pdf_path: string;
  records: BillingRecord[];
  flagged: FlaggedRecord[];
  created_at: string;
  completed_at: string | null;
  token_usage: TokenUsage | null;
  cost_usd: number | null;
  processing_duration_seconds: number | null;
  error: string | null;
}
