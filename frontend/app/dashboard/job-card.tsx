"use client";

import Link from "next/link";

import { fileName } from "@/lib/format";
import { groupRecordsByInvoice } from "@/lib/invoices";
import type { Job } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import { ArrowRight } from "@/components/icons";

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/** Compact job row. Links to the per-document report at /dashboard/jobs/[id]. */
export function JobCard({
  job,
  onCancel,
}: {
  job: Job;
  onCancel: (jobId: string) => void;
}) {
  const name = fileName(job.pdf_path);
  const invoiceCount = groupRecordsByInvoice(job.records).length;
  const cached = job.status === "completed" && job.processing_duration_seconds === 0;

  return (
    <li className="card-link">
      <div className="flex items-center gap-3 px-4 py-3">
        <Link
          href={`/dashboard/jobs/${job.job_id}`}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-lg"
        >
          <StatusBadge status={job.status} />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-800">{name}</div>
            <div className="flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
              <span>{timeAgo(job.created_at)}</span>
              {job.records.length > 0 && (
                <span>· {job.records.length} record{job.records.length === 1 ? "" : "s"}</span>
              )}
              {invoiceCount > 0 && (
                <span>· {invoiceCount} invoice{invoiceCount === 1 ? "" : "s"}</span>
              )}
              {job.flagged.length > 0 && (
                <span className="font-medium text-amber-700">· {job.flagged.length} flagged</span>
              )}
            </div>
          </div>
        </Link>

        {cached && (
          <span
            className="badge hidden bg-violet-100 text-violet-700 sm:inline-flex"
            title="Reused a previous extraction of identical content"
          >
            cached
          </span>
        )}
        {job.status === "pending" && (
          <button onClick={() => onCancel(job.job_id)} className="btn btn-secondary btn-sm">
            Cancel
          </button>
        )}
        <ArrowRight className="h-4 w-4 shrink-0 text-slate-300" />
      </div>
    </li>
  );
}
