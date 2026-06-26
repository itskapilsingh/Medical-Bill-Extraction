"use client";

import { usePagedJobs, useSummary } from "@/lib/use-jobs";
import { ReportSection } from "../report-section";

export function RecordsClient() {
  const { jobs, loading, loadingMore, loadError, hasMore, loadMore } = usePagedJobs(50);
  const { summary } = useSummary();

  if (loading) {
    return <div className="skeleton h-64 rounded-2xl" />;
  }

  if (loadError) {
    return (
      <p
        role="alert"
        className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
      >
        {loadError}
      </p>
    );
  }

  return (
    <ReportSection
      jobs={jobs}
      summary={summary}
      hasMore={hasMore}
      loadingMore={loadingMore}
      onLoadMore={loadMore}
    />
  );
}
