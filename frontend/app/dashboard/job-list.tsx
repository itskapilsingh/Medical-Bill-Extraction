"use client";

import { useMemo, useState } from "react";

import { fileName } from "@/lib/format";
import type { Job, JobStatus } from "@/lib/types";
import { JobCard } from "./job-card";

const STATUS_FILTERS: { value: JobStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "completed", label: "Completed" },
  { value: "processing", label: "Processing" },
  { value: "pending", label: "Pending" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

/** Full, filterable document list (status + file-name search + needs-review). */
export function JobList({
  jobs,
  onCancel,
}: {
  jobs: Job[];
  onCancel: (jobId: string) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<JobStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return jobs.filter((job) => {
      if (statusFilter !== "all" && job.status !== statusFilter) return false;
      if (flaggedOnly && job.flagged.length === 0) return false;
      if (q && !fileName(job.pdf_path).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [jobs, statusFilter, query, flaggedOnly]);

  function clear() {
    setStatusFilter("all");
    setQuery("");
    setFlaggedOnly(false);
  }

  return (
    <div>
      <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by file name..."
          aria-label="Search documents by file name"
          className="input-base"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as JobStatus | "all")}
          aria-label="Filter documents by status"
          className="select-base"
        >
          {STATUS_FILTERS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
            checked={flaggedOnly}
            onChange={(e) => setFlaggedOnly(e.target.checked)}
          />
          Needs review
        </label>
      </div>

      <p className="sr-only" role="status" aria-live="polite">
        {`${visible.length} of ${jobs.length} document${jobs.length === 1 ? "" : "s"} shown.`}
      </p>

      {jobs.length === 0 ? (
        <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
          <div className="text-sm font-medium text-slate-700">No documents yet</div>
          <div className="mt-1 text-sm text-slate-500">
            Upload a billing PDF from the overview to extract its records.
          </div>
        </div>
      ) : visible.length === 0 ? (
        <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <div className="text-sm font-medium text-slate-700">No documents match these filters</div>
          <button
            onClick={clear}
            className="mt-2 text-sm font-medium text-teal-700 hover:text-teal-800"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <ul className="space-y-3">
          {visible.map((job) => (
            <JobCard key={job.job_id} job={job} onCancel={onCancel} />
          ))}
        </ul>
      )}
    </div>
  );
}
