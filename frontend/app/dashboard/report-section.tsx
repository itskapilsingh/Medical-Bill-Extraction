"use client";

import { useEffect, useMemo, useState } from "react";

import { money } from "@/lib/format";
import {
  DEFAULT_REPORT_FILTERS,
  filterReportRows,
  flattenReportRows,
  invoiceOptionLabel,
  reportFilterOptions,
  summarizeReportRows,
  type FinancialFilter,
  type ReportFilters,
  type ReportRow,
  type ReviewFilter,
} from "@/lib/reports";
import type { JobsSummary } from "@/lib/api";
import type { Job } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { AlertTriangle, FileText, Loader } from "@/components/icons";

const PAGE_SIZE = 50;
// The text search re-runs the flatten/filter over every loaded record. Debounce
// it so the work happens on a pause in typing, not on every keystroke.
const SEARCH_DEBOUNCE_MS = 200;
// Upper bound on how many flattened records the client will filter/render at
// once, so an unbounded "Load more" history can't make filtering janky. When the
// loaded set exceeds it we process the newest slice and tell the user (never a
// silent truncation). Server-side headline totals stay correct regardless.
const MAX_REPORT_ROWS = 2000;

export function ReportSection({
  jobs,
  summary = null,
  hasMore = false,
  loadingMore = false,
  onLoadMore,
}: {
  jobs: Job[];
  summary?: JobsSummary | null;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
}) {
  const [filters, setFilters] = useState<ReportFilters>(DEFAULT_REPORT_FILTERS);
  const [page, setPage] = useState(1);
  // Debounce only the free-text query (the select/date filters are discrete, so
  // they apply immediately). The input below stays bound to the live value for
  // instant feedback; the heavy filter keys off the debounced copy.
  const debouncedQuery = useDebouncedValue(filters.query, SEARCH_DEBOUNCE_MS);
  const allRows = useMemo(() => flattenReportRows(jobs), [jobs]);
  const truncated = allRows.length > MAX_REPORT_ROWS;
  const rows = useMemo(
    () => (truncated ? allRows.slice(0, MAX_REPORT_ROWS) : allRows),
    [allRows, truncated],
  );
  const options = useMemo(() => reportFilterOptions(rows), [rows]);
  const effectiveFilters = useMemo(
    () => ({ ...filters, query: debouncedQuery }),
    [filters, debouncedQuery],
  );
  const filteredRows = useMemo(
    () => filterReportRows(rows, effectiveFilters),
    [rows, effectiveFilters],
  );
  const filteredTotals = useMemo(() => summarizeReportRows(filteredRows), [filteredRows]);
  const hasRows = rows.length > 0;
  const hasActiveFilters =
    filters.query !== "" ||
    filters.provider !== "" ||
    filters.invoice !== "" ||
    filters.payer !== "" ||
    filters.review !== "all" ||
    filters.financial !== "all" ||
    filters.dateFrom !== "" ||
    filters.dateTo !== "";

  // Headline totals: when the user hasn't filtered, show the server-side global
  // totals (correct across ALL documents, not just the loaded page). Once they
  // filter, switch to the totals of the loaded+filtered rows they're exploring.
  const showGlobalTotals = summary !== null && !hasActiveFilters;
  const totals = showGlobalTotals
    ? {
        records: summary!.records_count,
        totalCharges: summary!.total_charges,
        insPaid: summary!.ins_paid,
        adjustment: summary!.adjustment,
        payments: summary!.payments,
        balance: summary!.balance,
      }
    : filteredTotals;
  const totalsLabel = showGlobalTotals
    ? "Totals across all completed records"
    : "Totals for the filtered records below";

  // Any applied filter change resets to the first page so the view never lands on
  // an empty page that no longer exists. Keyed on the effective (debounced)
  // filters so it follows the set the table actually shows.
  useEffect(() => {
    setPage(1);
  }, [effectiveFilters]);

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));

  // A background refresh can shrink the result set without a filter change; keep
  // `page` clamped so the pager buttons never act on a page that no longer exists.
  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  const safePage = Math.min(page, pageCount);
  const pageRows = filteredRows.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  function updateFilter<K extends keyof ReportFilters>(
    key: K,
    value: ReportFilters[K],
  ) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function clearFilters() {
    setFilters(DEFAULT_REPORT_FILTERS);
  }

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-sm font-semibold text-slate-900">Records report</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Filter extracted records across all your completed documents.
          </p>
        </div>
        <span className="badge bg-slate-100 text-slate-600">
          <FileText className="h-3.5 w-3.5" />
          {rows.length} record{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <label className="block sm:col-span-2 lg:col-span-1">
          <span className="mb-1 block text-xs font-medium text-slate-500">Search</span>
          <input
            type="search"
            value={filters.query}
            onChange={(event) => updateFilter("query", event.target.value)}
            placeholder="Provider, invoice, payer, CPT..."
            className="input-base"
          />
        </label>

        <ReportSelect
          label="Provider"
          value={filters.provider}
          onChange={(value) => updateFilter("provider", value)}
          options={options.providers.map((provider) => ({
            value: provider,
            label: provider,
          }))}
          allLabel="All providers"
        />

        <ReportSelect
          label="Payer"
          value={filters.payer}
          onChange={(value) => updateFilter("payer", value)}
          options={options.payers.map((payer) => ({ value: payer, label: payer }))}
          allLabel="All payers"
        />

        <ReportSelect
          label="Invoice"
          value={filters.invoice}
          onChange={(value) => updateFilter("invoice", value)}
          options={options.invoices.map((invoice) => ({
            value: invoice,
            label: invoiceOptionLabel(invoice),
          }))}
          allLabel="All invoices"
        />

        <ReportSelect
          label="Review"
          value={filters.review}
          onChange={(value) => updateFilter("review", value as ReviewFilter)}
          allValue="all"
          options={[
            { value: "needs_review", label: "Needs review" },
            { value: "clean", label: "Clean" },
          ]}
          allLabel="All"
        />

        <ReportSelect
          label="Financial"
          value={filters.financial}
          onChange={(value) => updateFilter("financial", value as FinancialFilter)}
          allValue="all"
          options={[
            { value: "has_balance", label: "Has balance" },
            { value: "has_charges", label: "Has charges" },
          ]}
          allLabel="All"
        />

        <DateField
          label="Treated from"
          value={filters.dateFrom}
          max={filters.dateTo || undefined}
          onChange={(value) => updateFilter("dateFrom", value)}
        />

        <DateField
          label="Treated to"
          value={filters.dateTo}
          min={filters.dateFrom || undefined}
          onChange={(value) => updateFilter("dateTo", value)}
        />

        <div className="flex items-end">
          <button
            type="button"
            onClick={clearFilters}
            disabled={!hasActiveFilters}
            className="btn btn-secondary h-10 w-full"
          >
            Clear filters
          </button>
        </div>
      </div>

      <p className="mt-4 text-xs font-medium text-slate-500">{totalsLabel}</p>
      <ReportTotals totals={totals} />

      {truncated && (
        <p
          role="status"
          className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          Showing the {MAX_REPORT_ROWS.toLocaleString()} most recent loaded records.
          Use the filters above to narrow down to the rows you need.
        </p>
      )}

      {onLoadMore && hasMore && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
          <span>
            The table shows your most recent documents. Load more to filter and browse
            across everything.
          </span>
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="btn btn-secondary btn-sm"
          >
            {loadingMore ? <Loader className="h-3.5 w-3.5" /> : null}
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}

      {!hasRows ? (
        <ReportEmptyState message="Completed extracted records will appear here." />
      ) : filteredRows.length === 0 ? (
        <ReportEmptyState message="No records match the selected filters." />
      ) : (
        <>
          <ReportTable rows={pageRows} />
          <ReportPager
            page={safePage}
            pageCount={pageCount}
            total={filteredRows.length}
            pageSize={PAGE_SIZE}
            onPrev={() => setPage((p) => Math.max(1, p - 1))}
            onNext={() => setPage((p) => Math.min(pageCount, p + 1))}
          />
        </>
      )}
    </section>
  );
}

function ReportSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
  allValue = "",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  allLabel: string;
  allValue?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="select-base"
      >
        <option value={allValue}>{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function DateField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <input
        type="date"
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(event.target.value)}
        className="input-base"
      />
    </label>
  );
}

function ReportPager({
  page,
  pageCount,
  total,
  pageSize,
  onPrev,
  onNext,
}: {
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (pageCount <= 1) {
    return (
      <p className="mt-3 text-xs text-slate-500">
        {total} record{total === 1 ? "" : "s"}
      </p>
    );
  }
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <div className="mt-3 flex items-center justify-between gap-3">
      <p className="text-xs text-slate-500" aria-live="polite">
        Showing {first.toLocaleString()}–{last.toLocaleString()} of{" "}
        {total.toLocaleString()}
      </p>
      <div className="flex items-center gap-2">
        <button type="button" onClick={onPrev} disabled={page <= 1} className="btn btn-secondary btn-sm">
          Previous
        </button>
        <span className="text-xs font-medium text-slate-500">
          Page {page} of {pageCount}
        </span>
        <button type="button" onClick={onNext} disabled={page >= pageCount} className="btn btn-secondary btn-sm">
          Next
        </button>
      </div>
    </div>
  );
}

function ReportTotals({
  totals,
}: {
  totals: {
    records: number;
    totalCharges: number;
    insPaid: number;
    adjustment: number;
    payments: number;
    balance: number;
  };
}) {
  const items = [
    ["Records", totals.records.toLocaleString()],
    ["Total charges", money(totals.totalCharges)],
    ["Insurance paid", money(totals.insPaid)],
    ["Adjustments", money(totals.adjustment)],
    ["Patient paid", money(totals.payments)],
    ["Balance", money(totals.balance)],
  ];

  return (
    <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-6">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <div className="text-xs font-medium text-slate-500">{label}</div>
          <div className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
            {value}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportEmptyState({ message }: { message: string }) {
  return (
    <div className="mt-4 grid place-items-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center">
      <FileText className="mb-2 h-7 w-7 text-slate-300" />
      <div className="text-sm font-medium text-slate-600">{message}</div>
    </div>
  );
}

function ReportTable({ rows }: { rows: ReportRow[] }) {
  return (
    <div
      role="region"
      aria-label="Records (scroll horizontally for all columns)"
      tabIndex={0}
      className="scrollbar-thin mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white"
    >
      <table className="min-w-[1180px] w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] uppercase tracking-wider text-slate-500">
            <th className="px-3 py-2.5 font-medium">File</th>
            <th className="px-3 py-2.5 font-medium">Invoice</th>
            <th className="px-3 py-2.5 font-medium">Provider</th>
            <th className="px-3 py-2.5 font-medium">Date</th>
            <th className="px-3 py-2.5 font-medium">CPT / Payer</th>
            <th className="px-3 py-2.5 text-right font-medium">Charges</th>
            <th className="px-3 py-2.5 text-right font-medium">Ins. paid</th>
            <th className="px-3 py-2.5 text-right font-medium">Adjustment</th>
            <th className="px-3 py-2.5 text-right font-medium">Payments</th>
            <th className="px-3 py-2.5 text-right font-medium">Balance</th>
            <th className="px-3 py-2.5 font-medium">Page</th>
            <th className="px-3 py-2.5 font-medium">Review</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.id} className="align-top transition hover:bg-slate-50">
              <td className="max-w-44 truncate px-3 py-2.5 text-slate-700" title={row.sourceFile}>
                {row.sourceFile}
              </td>
              <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">
                {row.invoiceNumber ?? "—"}
              </td>
              <td className="px-3 py-2.5 text-slate-800">{row.provider}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">
                {row.treatmentDate}
              </td>
              <td className="px-3 py-2.5">
                <div className="text-xs font-medium text-slate-600">
                  {row.cptCodes.join(", ") || "—"}
                </div>
                {row.payers.length > 0 && (
                  <div className="mt-0.5 text-xs text-slate-500">
                    {row.payers.join(", ")}
                  </div>
                )}
              </td>
              <MoneyCell value={row.totalCharges} />
              <MoneyCell value={row.insPaid} />
              <MoneyCell value={row.adjustment} />
              <MoneyCell value={row.payments} />
              <MoneyCell value={row.balance} strong />
              <td className="whitespace-nowrap px-3 py-2.5 text-slate-500">{row.page}</td>
              <td className="px-3 py-2.5">
                {row.needsReview ? (
                  <span
                    title={row.reviewReasons.join(" | ")}
                    className="badge bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200"
                  >
                    <AlertTriangle className="h-3 w-3" />
                    Needs review
                  </span>
                ) : (
                  <span className="badge bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200">
                    Clean
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MoneyCell({ value, strong = false }: { value: number | null; strong?: boolean }) {
  return (
    <td
      className={`whitespace-nowrap px-3 py-2.5 text-right tabular-nums ${
        strong ? "font-medium text-slate-900" : "text-slate-700"
      }`}
    >
      {money(value)}
    </td>
  );
}
