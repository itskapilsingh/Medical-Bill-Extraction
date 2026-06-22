"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { signOut } from "@/lib/auth-client";
import { cancelJob, listJobs, uploadPdf } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/types";
import { JobCard } from "./job-card";

const LIVE_STATUSES: JobStatus[] = ["pending", "processing"];

export default function DashboardClient({
  userEmail,
  userName,
}: {
  userEmail: string;
  userName: string;
}) {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [bypassCache, setBypassCache] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setJobs(await listJobs());
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, []);

  // Initial load + poll while any job is still in flight.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const hasLive = jobs.some((j) => LIVE_STATUSES.includes(j.status));
    if (!hasLive) return;
    const id = setInterval(() => void refresh(), 2500);
    return () => clearInterval(id);
  }, [jobs, refresh]);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadPdf(file, bypassCache);
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onCancel(jobId: string) {
    try {
      await cancelJob(jobId);
      await refresh();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function onSignOut() {
    await signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--color-line)] bg-[var(--color-surface)]">
        <div className="max-w-5xl mx-auto px-5 h-14 flex items-center justify-between">
          <span className="font-semibold">Medical Billing Extraction</span>
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--color-muted)]" title={userEmail}>
              {userName}
            </span>
            <button className="btn btn-ghost" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-5 py-8 space-y-8">
        <section className="card p-5">
          <h2 className="font-semibold mb-1">Upload a billing PDF</h2>
          <p className="text-sm text-[var(--color-muted)] mb-4">
            The document is processed asynchronously. Results appear below and are
            visible only to your account.
          </p>
          <form onSubmit={onUpload} className="flex flex-wrap items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              required
              className="text-sm file:mr-3 file:btn file:btn-ghost"
            />
            <label className="flex items-center gap-2 text-sm text-[var(--color-muted)]">
              <input
                type="checkbox"
                checked={bypassCache}
                onChange={(e) => setBypassCache(e.target.checked)}
              />
              Bypass cache
            </label>
            <button type="submit" className="btn btn-primary" disabled={uploading}>
              {uploading ? "Uploading…" : "Upload & extract"}
            </button>
          </form>
          {uploadError && (
            <p className="mt-3 text-sm text-red-600">{uploadError}</p>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Your jobs</h2>
            <button className="btn btn-ghost" onClick={() => void refresh()}>
              Refresh
            </button>
          </div>

          {loadError && <p className="text-sm text-red-600 mb-3">{loadError}</p>}

          {jobs.length === 0 ? (
            <div className="card p-8 text-center text-sm text-[var(--color-muted)]">
              No jobs yet. Upload a PDF to get started.
            </div>
          ) : (
            <ul className="space-y-3">
              {jobs.map((job) => (
                <JobCard key={job.job_id} job={job} onCancel={onCancel} />
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
