// Client-side helpers. Every call goes to the same-origin BFF proxy
// (/api/backend/*), which attaches the session and forwards to the FastAPI API.

import type { Job } from "@/lib/types";

export interface UploadBatchResult {
  accepted: Job[];
  failed: { file: File; error: unknown }[];
}

export class ApiError extends Error {
  status: number;
  /** Seconds to wait before retrying, parsed from a 429's Retry-After / body. */
  retryAfter?: number;
  constructor(message: string, status: number, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

function positiveInt(value: unknown): number | undefined {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : undefined;
}

async function toError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  // Prefer the Retry-After header; fall back to the body's retry_after_seconds.
  let retryAfter = positiveInt(res.headers.get("retry-after"));
  try {
    const body = await res.json();
    if (typeof body?.message === "string" && body.message) message = body.message;
    else if (typeof body?.error === "string" && body.error) message = body.error;
    retryAfter ??= positiveInt(body?.error?.retry_after_seconds);
  } catch {
    // non-JSON body — keep the generic message
  }
  return new ApiError(message, res.status, retryAfter);
}

/** Server-computed aggregate across ALL the caller's jobs (correct at any scale). */
export interface JobsSummary {
  total: number;
  completed: number;
  processing: number;
  pending: number;
  failed: number;
  cancelled: number;
  records_count: number;
  flagged_count: number;
  total_charges: number;
  ins_paid: number;
  adjustment: number;
  payments: number;
  balance: number;
}

export async function getJobsSummary(): Promise<JobsSummary> {
  const res = await fetch("/api/backend/jobs/summary", { cache: "no-store" });
  if (!res.ok) throw await toError(res);
  return res.json();
}

/**
 * One page of the caller's jobs, newest first. The server caps limit at 200.
 *
 * Prefer the `before` keyset cursor (the last/oldest row already shown) over
 * `offset`: it stays correct when new jobs land at the head between pages and
 * avoids deep-offset scans. `offset` is kept for simple first-page-only callers.
 */
export async function listJobs(opts?: {
  limit?: number;
  offset?: number;
  before?: { createdAt: string; id: string };
}): Promise<Job[]> {
  const qs = new URLSearchParams();
  if (opts?.limit != null) qs.set("limit", String(opts.limit));
  if (opts?.before) {
    qs.set("before_created_at", opts.before.createdAt);
    qs.set("before_id", opts.before.id);
  } else if (opts?.offset != null) {
    qs.set("offset", String(opts.offset));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(`/api/backend/jobs${suffix}`, { cache: "no-store" });
  if (!res.ok) throw await toError(res);
  return res.json();
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`/api/backend/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw await toError(res);
  return res.json();
}

export async function uploadPdf(file: File, bypassCache = false): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  const qs = bypassCache ? "?bypass_cache=true" : "";
  const res = await fetch(`/api/backend/jobs${qs}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw await toError(res);
  return res.json();
}

export async function uploadPdfs(
  files: File[],
  bypassCache = false,
): Promise<UploadBatchResult> {
  const results = await Promise.all(
    files.map(async (file) => {
      try {
        return { status: "accepted" as const, job: await uploadPdf(file, bypassCache) };
      } catch (error) {
        return { status: "failed" as const, file, error };
      }
    }),
  );

  return results.reduce<UploadBatchResult>(
    (acc, result) => {
      if (result.status === "accepted") acc.accepted.push(result.job);
      else acc.failed.push({ file: result.file, error: result.error });
      return acc;
    },
    { accepted: [], failed: [] },
  );
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`/api/backend/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw await toError(res);
}
