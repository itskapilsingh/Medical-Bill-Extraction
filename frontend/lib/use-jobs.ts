"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  ApiError,
  cancelJob,
  getJobsSummary,
  listJobs,
  type JobsSummary,
} from "@/lib/api";
import { useToast } from "@/components/toast";
import type { Job, JobStatus } from "@/lib/types";

const LIVE_STATUSES: JobStatus[] = ["pending", "processing"];

// The dashboard only renders a short "recent" preview, but it polls every few
// seconds while jobs are live. Fetching the caller's ENTIRE history (with every
// job's full records[]) on each poll is wasteful and grows without bound, so the
// preview poll is capped to a small newest-first window. It comfortably covers
// the rendered preview plus any just-uploaded job (always at the head), so the
// live-poll keeps running until that job settles.
const RECENT_POLL_LIMIT = 25;

/**
 * Shared job state: load the caller's jobs, poll while any are live, cancel, and
 * fold a 401 into a one-time toast + redirect. Backs the dashboard's recent
 * preview; the page caps the fetch to the newest `limit` jobs.
 */
export function useJobs(limit: number = RECENT_POLL_LIMIT) {
  const router = useRouter();
  const toast = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const expiryNotified = useRef(false);

  const handleAuthExpiry = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        if (!expiryNotified.current) {
          expiryNotified.current = true;
          toast.info("Your session has expired. Please sign in again.");
        }
        router.push("/login");
        router.refresh();
        return true;
      }
      return false;
    },
    [router, toast],
  );

  const refresh = useCallback(async () => {
    try {
      setJobs(await listJobs({ limit }));
      setLoadError(null);
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setLoadError(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, [handleAuthExpiry, limit]);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!jobs.some((j) => LIVE_STATUSES.includes(j.status))) return;
    const id = setInterval(() => void refresh(), 2500);
    return () => clearInterval(id);
  }, [jobs, refresh]);

  const onCancel = useCallback(
    async (jobId: string) => {
      try {
        await cancelJob(jobId);
        toast.success("Job cancelled.");
        await refresh();
      } catch (err) {
        if (handleAuthExpiry(err)) return;
        toast.error(err instanceof Error ? err.message : "Could not cancel the job.");
      }
    },
    [handleAuthExpiry, refresh, toast],
  );

  return { jobs, loading, loadError, refresh, onCancel, handleAuthExpiry };
}

/**
 * Server-side aggregate of the caller's jobs (counts + financial totals). Correct
 * regardless of how many documents exist — unlike summing a paged list client-side.
 * Polls while anything is still pending/processing so the numbers settle live.
 */
export function useSummary() {
  const router = useRouter();
  const [summary, setSummary] = useState<JobsSummary | null>(null);

  const refreshSummary = useCallback(async () => {
    try {
      setSummary(await getJobsSummary());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        router.refresh();
      }
    }
  }, [router]);

  useEffect(() => {
    void refreshSummary();
  }, [refreshSummary]);

  useEffect(() => {
    if (!summary || (summary.processing === 0 && summary.pending === 0)) return;
    const id = setInterval(() => void refreshSummary(), 3000);
    return () => clearInterval(id);
  }, [summary, refreshSummary]);

  return { summary, refreshSummary };
}

/**
 * Offset-paginated job list for the full Documents / Records views: loads the
 * first page, then appends pages on demand so the whole history is reachable
 * without ever shipping everything in one response.
 */
export function usePagedJobs(pageSize = 50) {
  const router = useRouter();
  const toast = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const expiryNotified = useRef(false);

  const handleAuthExpiry = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        if (!expiryNotified.current) {
          expiryNotified.current = true;
          toast.info("Your session has expired. Please sign in again.");
        }
        router.push("/login");
        router.refresh();
        return true;
      }
      return false;
    },
    [router, toast],
  );

  const refresh = useCallback(async () => {
    try {
      const page = await listJobs({ limit: pageSize, offset: 0 });
      setJobs(page);
      setHasMore(page.length === pageSize);
      setLoadError(null);
    } catch (err) {
      if (handleAuthExpiry(err)) return;
      setLoadError(err instanceof Error ? err.message : "Failed to load jobs");
    }
  }, [pageSize, handleAuthExpiry]);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      // Keyset, not offset: page from the oldest row already loaded. New jobs
      // arriving at the head between pages can't shift a row across the page
      // boundary, so nothing is skipped or duplicated (REL-004 / PERF-005).
      const last = jobs[jobs.length - 1];
      const page = await listJobs({
        limit: pageSize,
        before: last
          ? { createdAt: last.created_at, id: last.job_id }
          : undefined,
      });
      setJobs((current) => [...current, ...page]);
      setHasMore(page.length === pageSize);
    } catch (err) {
      if (!handleAuthExpiry(err)) {
        toast.error(err instanceof Error ? err.message : "Failed to load more.");
      }
    } finally {
      setLoadingMore(false);
    }
  }, [jobs, pageSize, handleAuthExpiry, toast]);

  const onCancel = useCallback(
    async (jobId: string) => {
      try {
        await cancelJob(jobId);
        toast.success("Job cancelled.");
        await refresh();
      } catch (err) {
        if (handleAuthExpiry(err)) return;
        toast.error(err instanceof Error ? err.message : "Could not cancel the job.");
      }
    },
    [handleAuthExpiry, refresh, toast],
  );

  return { jobs, loading, loadingMore, loadError, hasMore, loadMore, refresh, onCancel };
}
