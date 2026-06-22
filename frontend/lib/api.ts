// Client-side helpers. Every call goes to the same-origin BFF proxy
// (/api/backend/*), which attaches the session and forwards to the FastAPI API.

import type { Job } from "@/lib/types";

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body?.message || body?.error || `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

export async function listJobs(): Promise<Job[]> {
  const res = await fetch("/api/backend/jobs", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getJob(jobId: string): Promise<Job> {
  const res = await fetch(`/api/backend/jobs/${jobId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
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
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`/api/backend/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await parseError(res));
}
