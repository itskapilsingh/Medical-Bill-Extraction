"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError, cancelJob, getJob } from "@/lib/api";
import { fileName } from "@/lib/format";
import type { Job, JobStatus } from "@/lib/types";
import { JobReport } from "@/components/job-report";
import { StatusBadge, STATUS } from "@/components/status-badge";
import { useToast } from "@/components/toast";
import { ArrowRight, RefreshCw } from "@/components/icons";

const LIVE_STATUSES: JobStatus[] = ["pending", "processing"];

export function JobDetailClient({ jobId }: { jobId: string }) {
  const router = useRouter();
  const toast = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setJob(await getJob(jobId));
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        router.refresh();
        return;
      }
      if (err instanceof ApiError && err.status === 404) {
        setNotFound(true);
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load the report.");
    }
  }, [jobId, router]);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!job || !LIVE_STATUSES.includes(job.status)) return;
    const id = setInterval(() => void refresh(), 2500);
    return () => clearInterval(id);
  }, [job, refresh]);

  async function onCancel() {
    try {
      await cancelJob(jobId);
      toast.success("Job cancelled.");
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not cancel the job.");
    }
  }

  const back = (
    <Link
      href="/dashboard"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
    >
      <ArrowRight className="h-4 w-4 rotate-180" />
      Back to documents
    </Link>
  );

  if (loading) {
    return (
      <div className="space-y-4">
        {back}
        <div className="skeleton h-48 rounded-2xl" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="space-y-4">
        {back}
        <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
          <div className="text-sm font-medium text-slate-700">Report not found</div>
          <div className="mt-1 text-sm text-slate-500">
            This document doesn&rsquo;t exist or isn&rsquo;t visible to your account.
          </div>
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="space-y-4">
        {back}
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {error ?? "Failed to load the report."}
        </p>
      </div>
    );
  }

  const cached = job.status === "completed" && job.processing_duration_seconds === 0;

  return (
    <div className="space-y-5">
      {back}
      <section className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-slate-900">
              {fileName(job.pdf_path)}
            </h1>
            {/* Polled status changes (processing → completed/failed) are visual
                only; mirror them into a polite live region so screen-reader
                users hear the document finish without reloading (WCAG 4.1.3). */}
            <p className="sr-only" role="status" aria-live="polite">
              Document status: {STATUS[job.status].label}.
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <StatusBadge status={job.status} />
              {cached && (
                <span
                  className="badge bg-violet-100 text-violet-700"
                  title="Reused a previous extraction of identical content"
                >
                  cached
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {job.status === "pending" && (
              <button onClick={onCancel} className="btn btn-secondary btn-sm">
                Cancel
              </button>
            )}
            <button onClick={() => void refresh()} className="btn btn-secondary btn-sm">
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>

        <div className="mt-4">
          <JobReport job={job} />
        </div>
      </section>
    </div>
  );
}
