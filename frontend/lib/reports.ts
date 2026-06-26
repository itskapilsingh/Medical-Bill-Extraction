import { fileName } from "@/lib/format";
import type { BillingRecord, FlaggedRecord, Job } from "@/lib/types";

export type ReviewFilter = "all" | "needs_review" | "clean";
export type FinancialFilter = "all" | "has_balance" | "has_charges";

export interface ReportFilters {
  query: string;
  provider: string;
  invoice: string;
  payer: string;
  review: ReviewFilter;
  financial: FinancialFilter;
  dateFrom: string; // "YYYY-MM-DD" (from <input type="date">) or ""
  dateTo: string;
}

export interface ReportRow {
  id: string;
  jobId: string;
  sourceFile: string;
  invoiceNumber: string | null;
  treatmentDate: string;
  /** Start ("YYYY-MM-DD") of the treatment date/range — also used for sort. Null = undated. */
  parsedDate: string | null;
  /** End of the treatment range (=== parsedDate for a single date). Null = undated. */
  parsedEndDate: string | null;
  cptCodes: string[];
  description: string | null;
  provider: string;
  insurers: string[];
  thirdParties: string[];
  payers: string[];
  totalCharges: number | null;
  insPaid: number | null;
  adjustment: number | null;
  payments: number | null;
  balance: number | null;
  page: string;
  needsReview: boolean;
  reviewReasons: string[];
}

export interface ReportTotals {
  records: number;
  totalCharges: number;
  insPaid: number;
  adjustment: number;
  payments: number;
  balance: number;
}

export const DEFAULT_REPORT_FILTERS: ReportFilters = {
  query: "",
  provider: "",
  invoice: "",
  payer: "",
  review: "all",
  financial: "all",
  dateFrom: "",
  dateTo: "",
};

// Matches an ISO (YYYY-M-D) or US (M/D/Y, M-D-Y) date token anywhere in a string.
const DATE_TOKEN = /(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})/g;

/** Return "YYYY-MM-DD" only if year/month/day form a real calendar date, else null. */
function isoIfValid(year: number, month: number, day: number): string | null {
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const dt = new Date(Date.UTC(year, month - 1, day));
  // Reject roll-overs like Feb 30 / Apr 31.
  if (
    dt.getUTCFullYear() !== year ||
    dt.getUTCMonth() !== month - 1 ||
    dt.getUTCDate() !== day
  ) {
    return null;
  }
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function* validDates(value: string): Generator<string> {
  DATE_TOKEN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = DATE_TOKEN.exec(value)) !== null) {
    let iso: string | null;
    if (match[1] !== undefined) {
      iso = isoIfValid(Number(match[1]), Number(match[2]), Number(match[3]));
    } else {
      let year = Number(match[6]);
      if (year < 100) year = year < 70 ? 2000 + year : 1900 + year;
      iso = isoIfValid(year, Number(match[4]), Number(match[5]));
    }
    if (iso) yield iso;
  }
}

/**
 * Pull the date(s) out of a free-form treatment_date. Returns the first and last
 * valid calendar dates found (start === end for a single date), so a multi-day
 * range like "03/16/2017 – 03/20/2017" yields {start: "2017-03-16", end:
 * "2017-03-20"}. Garbage / out-of-range tokens (e.g. "13/45/2017", "Various")
 * are rejected, so {start: null, end: null} means "undated".
 */
export function parseTreatmentDateRange(
  value: string | null | undefined,
): { start: string | null; end: string | null } {
  if (!value) return { start: null, end: null };
  const dates = Array.from(validDates(value));
  if (dates.length === 0) return { start: null, end: null };
  return { start: dates[0], end: dates[dates.length - 1] };
}

/** First valid date in a treatment_date as "YYYY-MM-DD" (for sort), or null. */
export function parseTreatmentDate(value: string | null | undefined): string | null {
  return parseTreatmentDateRange(value).start;
}

export const MISSING_INVOICE_VALUE = "__missing_invoice__";
export const MISSING_INVOICE_LABEL = "Invoice not found";

function normalizedInvoice(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function invoiceFilterValue(invoiceNumber: string | null): string {
  return invoiceNumber ?? MISSING_INVOICE_VALUE;
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function flagsForRows(flags: FlaggedRecord[]): {
  documentFlags: FlaggedRecord[];
  rowFlags: Map<number, FlaggedRecord[]>;
} {
  const documentFlags: FlaggedRecord[] = [];
  const rowFlags = new Map<number, FlaggedRecord[]>();

  for (const flag of flags) {
    if (flag.row === null) {
      documentFlags.push(flag);
      continue;
    }
    const existing = rowFlags.get(flag.row) ?? [];
    existing.push(flag);
    rowFlags.set(flag.row, existing);
  }

  return { documentFlags, rowFlags };
}

export function flattenReportRows(jobs: Job[]): ReportRow[] {
  const rows: ReportRow[] = [];

  for (const job of jobs) {
    if (job.status !== "completed" || job.records.length === 0) continue;

    const { documentFlags, rowFlags } = flagsForRows(job.flagged);
    job.records.forEach((record: BillingRecord, index) => {
      const flags = [...documentFlags, ...(rowFlags.get(index) ?? [])];
      const invoiceNumber = normalizedInvoice(record.invoice_number);
      const dateRange = parseTreatmentDateRange(record.treatment_date);
      rows.push({
        id: `${job.job_id}:${index}`,
        jobId: job.job_id,
        sourceFile: fileName(job.pdf_path),
        invoiceNumber,
        treatmentDate: record.treatment_date,
        parsedDate: dateRange.start,
        parsedEndDate: dateRange.end,
        cptCodes: record.cpt_codes,
        description: record.description,
        provider: record.provider,
        insurers: record.insurers,
        thirdParties: record.third_parties,
        payers: unique([...record.insurers, ...record.third_parties]),
        totalCharges: record.total_charges,
        insPaid: record.ins_paid,
        adjustment: record.adjustment,
        payments: record.payments,
        balance: record.balance,
        page: record.page,
        needsReview: flags.length > 0,
        reviewReasons: flags.map((flag) => flag.reason),
      });
    });
  }

  return rows;
}

function searchText(row: ReportRow): string {
  return [
    row.sourceFile,
    row.invoiceNumber ?? MISSING_INVOICE_LABEL,
    row.provider,
    row.description ?? "",
    row.page,
    row.cptCodes.join(" "),
    row.payers.join(" "),
  ]
    .join(" ")
    .toLowerCase();
}

function hasMoney(value: number | null): boolean {
  return typeof value === "number" && value !== 0;
}

export function filterReportRows(
  rows: ReportRow[],
  filters: ReportFilters,
): ReportRow[] {
  const query = filters.query.trim().toLowerCase();

  return rows.filter((row) => {
    if (query && !searchText(row).includes(query)) return false;
    if (filters.provider && row.provider !== filters.provider) return false;
    if (filters.invoice && invoiceFilterValue(row.invoiceNumber) !== filters.invoice) {
      return false;
    }
    if (filters.payer && !row.payers.includes(filters.payer)) return false;
    if (filters.review === "needs_review" && !row.needsReview) return false;
    if (filters.review === "clean" && row.needsReview) return false;
    if (filters.financial === "has_balance" && !hasMoney(row.balance)) return false;
    if (filters.financial === "has_charges" && !hasMoney(row.totalCharges)) {
      return false;
    }
    // Date range: keep a row whose treatment interval [start, end] OVERLAPS the
    // requested window. A row with no parseable date is excluded once a bound is
    // set. Comparing both ends (not just the start) means a multi-day service
    // that straddles the window boundary is not silently dropped.
    if (filters.dateFrom || filters.dateTo) {
      const start = row.parsedDate;
      const end = row.parsedEndDate ?? start;
      if (start === null || end === null) return false;
      if (filters.dateFrom && end < filters.dateFrom) return false; // ends before window
      if (filters.dateTo && start > filters.dateTo) return false; // starts after window
    }
    return true;
  });
}

function sum(rows: ReportRow[], key: keyof ReportRow): number {
  return rows.reduce((total, row) => {
    const value = row[key];
    return typeof value === "number" ? total + value : total;
  }, 0);
}

export function summarizeReportRows(rows: ReportRow[]): ReportTotals {
  return {
    records: rows.length,
    totalCharges: sum(rows, "totalCharges"),
    insPaid: sum(rows, "insPaid"),
    adjustment: sum(rows, "adjustment"),
    payments: sum(rows, "payments"),
    balance: sum(rows, "balance"),
  };
}

export function invoiceOptionLabel(value: string): string {
  return value === MISSING_INVOICE_VALUE ? MISSING_INVOICE_LABEL : value;
}

export function reportFilterOptions(rows: ReportRow[]): {
  providers: string[];
  invoices: string[];
  payers: string[];
} {
  return {
    providers: unique(rows.map((row) => row.provider)).sort((a, b) =>
      a.localeCompare(b),
    ),
    invoices: unique(rows.map((row) => invoiceFilterValue(row.invoiceNumber))).sort(
      (a, b) => invoiceOptionLabel(a).localeCompare(invoiceOptionLabel(b)),
    ),
    payers: unique(rows.flatMap((row) => row.payers)).sort((a, b) =>
      a.localeCompare(b),
    ),
  };
}
