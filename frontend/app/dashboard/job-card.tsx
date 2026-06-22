"use client";

import { useState } from "react";

import type { BillingRecord, FlaggedRecord, Job, JobStatus } from "@/lib/types";

const STATUS_STYLES: Record<JobStatus, string> = {
  pending: "bg-slate-100 text-slate-700",
  processing: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-zinc-100 text-zinc-600",
};

const SEVERITY_STYLES: Record<FlaggedRecord["severity"], string> = {
  low: "bg-amber-50 text-amber-700 border-amber-200",
  medium: "bg-orange-50 text-orange-700 border-orange-200",
  high: "bg-red-50 text-red-700 border-red-200",
};

function money(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fileName(path: string): string {
  return path.split("/").pop() ?? path;
}

function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge ${STATUS_STYLES[status]}`}>{status}</span>;
}

export function JobCard({
  job,
  onCancel,
}: {
  job: Job;
  onCancel: (jobId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasResult = job.records.length > 0 || job.flagged.length > 0;

  return (
    <li className="card overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          className="flex-1 flex items-center gap-3 text-left"
          onClick={() => setOpen((v) => !v)}
        >
          <StatusBadge status={job.status} />
          <span className="font-medium truncate">{fileName(job.pdf_path)}</span>
          {job.records.length > 0 && (
            <span className="text-xs text-[var(--color-muted)]">
              {job.records.length} record{job.records.length === 1 ? "" : "s"}
            </span>
          )}
          {job.flagged.length > 0 && (
            <span className="text-xs text-amber-700">
              {job.flagged.length} flagged
            </span>
          )}
        </button>
        {job.status === "pending" && (
          <button className="btn btn-ghost" onClick={() => onCancel(job.job_id)}>
            Cancel
          </button>
        )}
        <button className="btn btn-ghost" onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "View"}
        </button>
      </div>

      {open && (
        <div className="border-t border-[var(--color-line)] px-4 py-4 space-y-4">
          {job.status === "failed" && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {job.error ?? "The worker failed to process this job."}
            </p>
          )}

          {!hasResult && job.status !== "failed" && (
            <p className="text-sm text-[var(--color-muted)]">
              {job.status === "completed"
                ? "No records were extracted from this document."
                : "Waiting for the worker to finish…"}
            </p>
          )}

          {job.flagged.length > 0 && <FlaggedList flagged={job.flagged} />}
          {job.records.length > 0 && <RecordsTable records={job.records} />}

          <Metrics job={job} />
        </div>
      )}
    </li>
  );
}

function FlaggedList({ flagged }: { flagged: FlaggedRecord[] }) {
  return (
    <div>
      <h4 className="text-sm font-semibold mb-2">Flagged for review</h4>
      <ul className="space-y-2">
        {flagged.map((f, i) => (
          <li
            key={i}
            className={`text-sm border rounded-md px-3 py-2 ${SEVERITY_STYLES[f.severity]}`}
          >
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-semibold uppercase text-xs">{f.severity}</span>
              <span className="text-xs opacity-80">page {f.page}</span>
              {f.fields.length > 0 && (
                <span className="text-xs opacity-80">· {f.fields.join(", ")}</span>
              )}
            </div>
            {f.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecordsTable({ records }: { records: BillingRecord[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-[var(--color-muted)] border-b border-[var(--color-line)]">
            <th className="py-2 pr-3 font-medium">Treatment date</th>
            <th className="py-2 pr-3 font-medium">Provider</th>
            <th className="py-2 pr-3 font-medium">CPT</th>
            <th className="py-2 pr-3 font-medium text-right">Charges</th>
            <th className="py-2 pr-3 font-medium text-right">Ins. paid</th>
            <th className="py-2 pr-3 font-medium text-right">Adjustment</th>
            <th className="py-2 pr-3 font-medium text-right">Payments</th>
            <th className="py-2 pr-3 font-medium text-right">Balance</th>
            <th className="py-2 font-medium">Page</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r, i) => (
            <tr key={i} className="border-b border-[var(--color-line)] last:border-0 align-top">
              <td className="py-2 pr-3 whitespace-nowrap">{r.treatment_date}</td>
              <td className="py-2 pr-3">
                <div>{r.provider}</div>
                {(r.insurers.length > 0 || r.third_parties.length > 0) && (
                  <div className="text-xs text-[var(--color-muted)]">
                    {[...r.insurers, ...r.third_parties].join(", ")}
                  </div>
                )}
              </td>
              <td className="py-2 pr-3 text-xs">{r.cpt_codes.join(", ") || "—"}</td>
              <td className="py-2 pr-3 text-right whitespace-nowrap">{money(r.total_charges)}</td>
              <td className="py-2 pr-3 text-right whitespace-nowrap">{money(r.ins_paid)}</td>
              <td className="py-2 pr-3 text-right whitespace-nowrap">{money(r.adjustment)}</td>
              <td className="py-2 pr-3 text-right whitespace-nowrap">{money(r.payments)}</td>
              <td className="py-2 pr-3 text-right whitespace-nowrap">{money(r.balance)}</td>
              <td className="py-2 whitespace-nowrap">{r.page}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metrics({ job }: { job: Job }) {
  const items: [string, string][] = [];
  if (job.token_usage) {
    items.push(["Tokens", `${job.token_usage.total.toLocaleString()} (${job.token_usage.input} in / ${job.token_usage.output} out)`]);
  }
  if (job.cost_usd !== null) items.push(["Est. cost", `$${job.cost_usd.toFixed(4)}`]);
  if (job.processing_duration_seconds !== null) {
    items.push(["Duration", `${job.processing_duration_seconds.toFixed(1)}s`]);
  }
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--color-muted)] pt-1 border-t border-[var(--color-line)]">
      {items.map(([k, v]) => (
        <span key={k}>
          <span className="font-medium">{k}:</span> {v}
        </span>
      ))}
    </div>
  );
}
