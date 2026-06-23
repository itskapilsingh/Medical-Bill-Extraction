"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { signOut } from "@/lib/auth-client";
import { ApiError, cancelJob, listJobs, uploadPdf } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/types";
import {
  CheckCircle,
  FileText,
  Inbox,
  Loader,
  LogOut,
  RefreshCw,
  UploadCloud,
} from "@/components/icons";
import { JobCard } from "./job-card";

const LIVE_STATUSES: JobStatus[] = ["pending", "processing"];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function DashboardClient({
  userEmail,
  userName,
}: {
  userEmail: string;
  userName: string;
}) {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [bypassCache, setBypassCache] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleAuthExpiry = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        router.refresh();
        return true;
      }
      return false;
    },
    [router],
  );

  const refresh = useCallback(async () => {
    try {
      setJobs(await listJobs());
      setLoadError(null);
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setLoadError(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, [handleAuthExpiry]);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    const hasLive = jobs.some((j) => LIVE_STATUSES.includes(j.status));
    if (!hasLive) return;
    const id = setInterval(() => void refresh(), 2500);
    return () => clearInterval(id);
  }, [jobs, refresh]);

  const stats = useMemo(() => {
    const completed = jobs.filter((j) => j.status === "completed").length;
    const live = jobs.filter((j) => LIVE_STATUSES.includes(j.status)).length;
    const records = jobs.reduce((a, j) => a + j.records.length, 0);
    const flagged = jobs.reduce((a, j) => a + j.flagged.length, 0);
    return { total: jobs.length, completed, live, records, flagged };
  }, [jobs]);

  const isProcessing = stats.live > 0;

  function pickFile(f: File | null) {
    setUploadError(null);
    setFile(f);
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadPdf(file, bypassCache);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    } catch (err) {
      if (handleAuthExpiry(err)) return;
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
      if (handleAuthExpiry(err)) return;
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
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <div className="flex items-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.png"
              alt="Medical Bill Extraction"
              className="h-9 w-auto"
            />
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2.5 sm:flex">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-teal-100 text-xs font-semibold text-teal-700">
                {initials(userName)}
              </div>
              <div className="leading-tight">
                <div className="text-sm font-medium text-slate-700">{userName}</div>
                <div className="text-xs text-slate-400">{userEmail}</div>
              </div>
            </div>
            <button
              onClick={onSignOut}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        {/* Stats */}
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Documents" value={stats.total} />
          <StatCard label="Completed" value={stats.completed} accent="emerald" />
          <StatCard label="Records extracted" value={stats.records} accent="teal" />
          <StatCard label="Needs review" value={stats.flagged} accent="amber" />
        </section>

        {/* Upload */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Upload a billing PDF</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Processed asynchronously by the extraction agent. Results are visible only
            to your account.
          </p>

          <form onSubmit={onUpload} className="mt-4 space-y-3">
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pickFile(e.dataTransfer.files?.[0] ?? null);
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition ${
                dragging
                  ? "border-teal-400 bg-teal-50"
                  : "border-slate-300 bg-slate-50 hover:border-slate-400 hover:bg-slate-100/60"
              }`}
            >
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <div className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
                  <FileText className="h-4 w-4 text-teal-600" />
                  <span className="font-medium text-slate-800">{file.name}</span>
                  <span className="text-slate-400">{formatBytes(file.size)}</span>
                </div>
              ) : (
                <>
                  <UploadCloud className="h-7 w-7 text-slate-400" />
                  <div className="text-sm text-slate-600">
                    <span className="font-medium text-teal-600">Click to browse</span>{" "}
                    or drag &amp; drop a PDF
                  </div>
                </>
              )}
            </label>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <label
                className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-600"
                title="Always run a fresh extraction even if this file was processed before"
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                  checked={bypassCache}
                  onChange={(e) => setBypassCache(e.target.checked)}
                />
                Bypass cache
              </label>
              <button
                type="submit"
                disabled={uploading || !file}
                className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploading ? <Loader className="h-4 w-4" /> : <UploadCloud className="h-4 w-4" />}
                {uploading ? "Uploading…" : "Upload & extract"}
              </button>
            </div>
            {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}
          </form>
        </section>

        {/* Jobs */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Recent jobs</h2>
            <div className="flex items-center gap-3">
              {isProcessing && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600">
                  <Loader className="h-3.5 w-3.5" />
                  processing…
                </span>
              )}
              <button
                onClick={() => void refresh()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </button>
            </div>
          </div>

          {loadError && (
            <p className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {loadError}
            </p>
          )}

          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-16 rounded-xl" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
              <Inbox className="mb-3 h-9 w-9 text-slate-300" />
              <div className="text-sm font-medium text-slate-700">No documents yet</div>
              <div className="mt-1 text-sm text-slate-400">
                Upload a billing PDF above to extract its records.
              </div>
            </div>
          ) : (
            <ul className="space-y-3">
              {jobs.map((job) => (
                <JobCard key={job.job_id} job={job} onCancel={onCancel} />
              ))}
            </ul>
          )}
        </section>

        <footer className="flex items-center justify-center gap-1.5 pt-2 text-xs text-slate-400">
          <CheckCircle className="h-3.5 w-3.5" />
          Per-account isolation enforced at the database (RLS)
        </footer>
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent = "slate",
}: {
  label: string;
  value: number;
  accent?: "slate" | "emerald" | "teal" | "amber";
}) {
  const accents: Record<string, string> = {
    slate: "text-slate-900",
    emerald: "text-emerald-600",
    teal: "text-teal-600",
    amber: "text-amber-600",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${accents[accent]}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}
