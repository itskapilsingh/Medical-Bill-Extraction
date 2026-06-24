"use client";

import { useState } from "react";

import type { BillingRecord, FlaggedRecord, Job, JobStatus } from "@/lib/types";
import {
  AlertTriangle,
  Bolt,
  CheckCircle,
  ChevronDown,
  Clock,
  Coins,
  Loader,
  XCircle,
} from "@/components/icons";

const STATUS: Record<
  JobStatus,
  { label: string; cls: string; Icon: (p: { className?: string }) => React.ReactElement }
> = {
  completed: { label: "Completed", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", Icon: CheckCircle },
  processing: { label: "Processing", cls: "bg-blue-50 text-blue-700 ring-blue-200", Icon: Loader },
  pending: { label: "Pending", cls: "bg-slate-100 text-slate-600 ring-slate-200", Icon: Clock },
  failed: { label: "Failed", cls: "bg-red-50 text-red-700 ring-red-200", Icon: XCircle },
  cancelled: { label: "Cancelled", cls: "bg-zinc-100 text-zinc-500 ring-zinc-200", Icon: XCircle },
};

const SEVERITY: Record<FlaggedRecord["severity"], string> = {
  low: "border-amber-200 bg-amber-50 text-amber-800",
  medium: "border-orange-200 bg-orange-50 text-orange-800",
  high: "border-red-200 bg-red-50 text-red-800",
};

function money(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function sum(records: BillingRecord[], key: keyof BillingRecord): number | null {
  const vals = records
    .map((r) => r[key])
    .filter((v): v is number => typeof v === "number");
  return vals.length === 0 ? null : vals.reduce((a, b) => a + b, 0);
}

function fileName(path: string): string {
  return path.split("/").pop() ?? path;
}

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function StatusBadge({ status }: { status: JobStatus }) {
  const { label, cls, Icon } = STATUS[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
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
  const cached = job.status === "completed" && job.processing_duration_seconds === 0;

  return (
    <li className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={`job-detail-${job.job_id}`}
        >
          <StatusBadge status={job.status} />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-800">
              {fileName(job.pdf_path)}
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>{timeAgo(job.created_at)}</span>
              {job.records.length > 0 && (
                <span>· {job.records.length} record{job.records.length === 1 ? "" : "s"}</span>
              )}
              {job.flagged.length > 0 && (
                <span className="font-medium text-amber-600">
                  · {job.flagged.length} flagged
                </span>
              )}
            </div>
          </div>
          {cached && (
            <span
              className="hidden rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-700 sm:inline"
              title="Reused a previous extraction of identical content"
            >
              cached
            </span>
          )}
        </button>
        {job.status === "pending" && (
          <button
            onClick={() => onCancel(job.job_id)}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
          >
            Cancel
          </button>
        )}
        <button
          onClick={() => setOpen((v) => !v)}
          className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          aria-label={open ? "Collapse job details" : "Expand job details"}
          aria-expanded={open}
          aria-controls={`job-detail-${job.job_id}`}
        >
          <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} />
        </button>
      </div>

      {open && (
        <div
          id={`job-detail-${job.job_id}`}
          className="space-y-4 border-t border-slate-100 bg-slate-50/50 px-4 py-4"
        >
          {job.status === "failed" && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{job.error ?? "The worker failed to process this job."}</span>
            </div>
          )}

          {!hasResult && job.status !== "failed" && (
            <p className="text-sm text-slate-500">
              {job.status === "completed"
                ? "No records were extracted from this document."
                : "Waiting for the worker to finish…"}
            </p>
          )}

          {job.flagged.length > 0 && <FlaggedList flagged={job.flagged} />}
          {job.records.length > 0 && (
            <>
              <FinancialSummary records={job.records} />
              <RecordsTable records={job.records} />
            </>
          )}

          <Metrics job={job} />
        </div>
      )}
    </li>
  );
}

function FinancialSummary({ records }: { records: BillingRecord[] }) {
  const items: [string, number | null][] = [
    ["Total charges", sum(records, "total_charges")],
    ["Insurance paid", sum(records, "ins_paid")],
    ["Adjustments", sum(records, "adjustment")],
    ["Patient paid", sum(records, "payments")],
    ["Balance", sum(records, "balance")],
  ];
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
          <div className="text-xs text-slate-500">{label}</div>
          <div className="mt-0.5 font-semibold tabular-nums text-slate-900">
            {money(value)}
          </div>
        </div>
      ))}
    </div>
  );
}

function FlaggedList({ flagged }: { flagged: FlaggedRecord[] }) {
  return (
    <div>
      <h4 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-amber-800">
        <AlertTriangle className="h-4 w-4" />
        Flagged for review ({flagged.length})
      </h4>
      <ul className="space-y-2">
        {flagged.map((f, i) => (
          <li key={i} className={`rounded-lg border px-3 py-2 text-sm ${SEVERITY[f.severity]}`}>
            <div className="mb-0.5 flex items-center gap-2 text-xs">
              <span className="font-bold uppercase tracking-wide">{f.severity}</span>
              <span className="opacity-70">page {f.page}</span>
              {f.fields.length > 0 && (
                <span className="opacity-70">· {f.fields.join(", ")}</span>
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
    <div className="scrollbar-thin overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-3 py-2.5 font-medium">Treatment date</th>
            <th className="px-3 py-2.5 font-medium">Provider</th>
            <th className="px-3 py-2.5 font-medium">CPT</th>
            <th className="px-3 py-2.5 text-right font-medium">Charges</th>
            <th className="px-3 py-2.5 text-right font-medium">Ins. paid</th>
            <th className="px-3 py-2.5 text-right font-medium">Adjustment</th>
            <th className="px-3 py-2.5 text-right font-medium">Payments</th>
            <th className="px-3 py-2.5 text-right font-medium">Balance</th>
            <th className="px-3 py-2.5 font-medium">Page</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {records.map((r, i) => (
            <tr key={i} className="align-top transition hover:bg-slate-50">
              <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">{r.treatment_date}</td>
              <td className="px-3 py-2.5">
                <div className="text-slate-800">{r.provider}</div>
                {(r.insurers.length > 0 || r.third_parties.length > 0) && (
                  <div className="text-xs text-slate-500">
                    {[...r.insurers, ...r.third_parties].join(", ")}
                  </div>
                )}
              </td>
              <td className="px-3 py-2.5 text-xs text-slate-500">
                {r.cpt_codes.join(", ") || "—"}
              </td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-slate-700">{money(r.total_charges)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-slate-700">{money(r.ins_paid)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-slate-700">{money(r.adjustment)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-slate-700">{money(r.payments)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums font-medium text-slate-900">{money(r.balance)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-slate-500">{r.page}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metrics({ job }: { job: Job }) {
  const items: { Icon: (p: { className?: string }) => React.ReactElement; label: string; value: string }[] = [];
  if (job.token_usage) {
    items.push({
      Icon: Bolt,
      label: "Tokens",
      value: `${job.token_usage.total.toLocaleString()} (${job.token_usage.input} in / ${job.token_usage.output} out)`,
    });
  }
  if (job.cost_usd !== null) {
    items.push({ Icon: Coins, label: "Est. cost", value: `$${job.cost_usd.toFixed(4)}` });
  }
  if (job.processing_duration_seconds !== null) {
    items.push({ Icon: Clock, label: "Duration", value: `${job.processing_duration_seconds.toFixed(1)}s` });
  }
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5 border-t border-slate-200 pt-3 text-xs text-slate-500">
      {items.map(({ Icon, label, value }) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5 text-slate-400" />
          <span className="font-medium text-slate-600">{label}:</span> {value}
        </span>
      ))}
    </div>
  );
}
