// Client-side helpers. Every call goes to the same-origin BFF proxy
// (/api/backend/*), which attaches the session and forwards to the FastAPI API.

import type { Job } from "@/lib/types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function toError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    message = body?.message || body?.error || message;
  } catch {
    // non-JSON body — keep the generic message
  }
  return new ApiError(message, res.status);
}

export async function listJobs(): Promise<Job[]> {
  const res = await fetch("/api/backend/jobs", { cache: "no-store" });
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

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`/api/backend/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw await toError(res);
}
