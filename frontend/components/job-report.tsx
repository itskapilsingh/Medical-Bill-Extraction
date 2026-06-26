"use client";

import { money } from "@/lib/format";
import { groupRecordsByInvoice } from "@/lib/invoices";
import type { BillingRecord, FlaggedRecord, Job } from "@/lib/types";
import { AlertTriangle, Bolt, Clock, Coins, XCircle } from "@/components/icons";

const SEVERITY: Record<FlaggedRecord["severity"], string> = {
  low: "border-amber-200 bg-amber-50 text-amber-800",
  medium: "border-orange-200 bg-orange-50 text-orange-800",
  high: "border-red-200 bg-red-50 text-red-800",
};

function sum(records: BillingRecord[], key: keyof BillingRecord): number | null {
  const vals = records
    .map((r) => r[key])
    .filter((v): v is number => typeof v === "number");
  return vals.length === 0 ? null : vals.reduce((a, b) => a + b, 0);
}

/** The full extracted result for a single job: flags, invoice-grouped tables, metrics. */
export function JobReport({ job }: { job: Job }) {
  const invoiceGroups = groupRecordsByInvoice(job.records);
  const hasResult = job.records.length > 0 || job.flagged.length > 0;

  return (
    <div className="space-y-4">
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

      {job.records.length > 0 && <FinancialSummary records={job.records} />}
      {job.flagged.length > 0 && <FlaggedList flagged={job.flagged} />}

      {job.records.length > 0 && (
        <div className="space-y-4">
          {invoiceGroups.map((group) => (
            <section
              key={group.invoiceNumber ?? "__missing_invoice__"}
              className="space-y-3 rounded-lg border border-slate-200 bg-white p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-900">{group.label}</h3>
                <span className="text-xs font-medium text-slate-500">
                  {group.records.length} record{group.records.length === 1 ? "" : "s"}
                </span>
              </div>
              {invoiceGroups.length > 1 && <FinancialSummary records={group.records} />}
              <RecordsTable records={group.records} />
            </section>
          ))}
        </div>
      )}

      <Metrics job={job} />
    </div>
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
          <div className="mt-0.5 font-semibold tabular-nums text-slate-900">{money(value)}</div>
        </div>
      ))}
    </div>
  );
}

function FlaggedList({ flagged }: { flagged: FlaggedRecord[] }) {
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-amber-800">
        <AlertTriangle className="h-4 w-4" />
        Flagged for review ({flagged.length})
      </h3>
      <ul className="space-y-2">
        {flagged.map((f, i) => (
          <li key={i} className={`rounded-lg border px-3 py-2 text-sm ${SEVERITY[f.severity]}`}>
            <div className="mb-0.5 flex items-center gap-2 text-xs">
              <span className="font-bold uppercase tracking-wide">{f.severity}</span>
              <span className="opacity-70">page {f.page}</span>
              {f.fields.length > 0 && <span className="opacity-70">· {f.fields.join(", ")}</span>}
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
    <div
      role="region"
      aria-label="Billing records (scroll horizontally for all columns)"
      tabIndex={0}
      className="scrollbar-thin overflow-x-auto rounded-lg border border-slate-200 bg-white"
    >
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] uppercase tracking-wider text-slate-500">
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
              <td className="px-3 py-2.5 text-xs text-slate-500">{r.cpt_codes.join(", ") || "—"}</td>
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
