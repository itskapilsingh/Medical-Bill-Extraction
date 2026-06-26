"use client";

import Link from "next/link";

import { usePagedJobs } from "@/lib/use-jobs";
import { ArrowRight, Loader, RefreshCw } from "@/components/icons";
import { JobList } from "../job-list";

export function DocumentsClient() {
  const { jobs, loading, loadingMore, loadError, hasMore, loadMore, refresh, onCancel } =
    usePagedJobs(50);

  return (
    <div className="space-y-4">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 transition hover:text-slate-900"
      >
        <ArrowRight className="h-4 w-4 rotate-180" />
        Back to overview
      </Link>

      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">All documents</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Every PDF you&rsquo;ve uploaded, searchable and filterable.
          </p>
        </div>
        <button onClick={() => void refresh()} className="btn btn-secondary btn-sm shrink-0">
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {loadError && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {loadError}
        </p>
      )}

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton h-16 rounded-xl" />
          ))}
        </div>
      ) : (
        <>
          <JobList jobs={jobs} onCancel={onCancel} />
          {hasMore && (
            <div className="mt-3 flex justify-center">
              <button
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="btn btn-secondary"
              >
                {loadingMore ? <Loader className="h-4 w-4" /> : null}
                {loadingMore ? "Loading…" : "Load more documents"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
