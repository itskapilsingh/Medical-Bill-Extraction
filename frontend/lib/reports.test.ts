import { describe, expect, it } from "vitest";

import {
  DEFAULT_REPORT_FILTERS,
  MISSING_INVOICE_VALUE,
  filterReportRows,
  flattenReportRows,
  parseTreatmentDate,
  parseTreatmentDateRange,
  reportFilterOptions,
  summarizeReportRows,
} from "@/lib/reports";
import type { BillingRecord, FlaggedRecord, Job } from "@/lib/types";

function record(overrides: Partial<BillingRecord> = {}): BillingRecord {
  return {
    invoice_number: "INV-100",
    treatment_date: "01/01/2026",
    cpt_codes: ["99213"],
    description: "Office visit",
    provider: "Alpha Clinic",
    insurers: ["Example Health"],
    third_parties: [],
    total_charges: 100,
    ins_paid: 60,
    adjustment: 20,
    payments: 5,
    balance: 15,
    page: "1",
    ...overrides,
  };
}

function flag(overrides: Partial<FlaggedRecord> = {}): FlaggedRecord {
  return {
    row: 0,
    fields: ["balance"],
    reason: "Balance unclear",
    page: "1",
    severity: "medium",
    ...overrides,
  };
}

function job(overrides: Partial<Job> = {}): Job {
  return {
    job_id: "job-1",
    status: "completed",
    pdf_path: "/app/pdfs/user/source-a.pdf",
    records: [record()],
    flagged: [],
    created_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:01:00Z",
    token_usage: null,
    cost_usd: null,
    processing_duration_seconds: null,
    error: null,
    ...overrides,
  };
}

describe("flattenReportRows", () => {
  it("uses only completed jobs with records and keeps source metadata", () => {
    const rows = flattenReportRows([
      job(),
      job({ job_id: "pending", status: "pending", records: [record()] }),
      job({ job_id: "failed", status: "failed", records: [record()] }),
      job({ job_id: "empty", records: [] }),
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: "job-1:0",
      jobId: "job-1",
      sourceFile: "source-a.pdf",
      invoiceNumber: "INV-100",
      provider: "Alpha Clinic",
    });
  });

  it("maps row-level and document-level flags to review status", () => {
    const rows = flattenReportRows([
      job({
        records: [
          record({ provider: "Alpha Clinic" }),
          record({ provider: "Beta Clinic", invoice_number: "INV-200" }),
        ],
        flagged: [flag({ row: 1, reason: "Payer unclear" })],
      }),
      job({
        job_id: "job-2",
        pdf_path: "/app/pdfs/user/source-b.pdf",
        records: [record({ provider: "Gamma Clinic" })],
        flagged: [flag({ row: null, reason: "Document totals unclear" })],
      }),
    ]);

    expect(rows.map((row) => [row.provider, row.needsReview])).toEqual([
      ["Alpha Clinic", false],
      ["Beta Clinic", true],
      ["Gamma Clinic", true],
    ]);
    expect(rows[1]?.reviewReasons).toEqual(["Payer unclear"]);
    expect(rows[2]?.reviewReasons).toEqual(["Document totals unclear"]);
  });
});

describe("filterReportRows", () => {
  const rows = flattenReportRows([
    job({
      records: [
        record({
          invoice_number: "INV-100",
          provider: "Alpha Clinic",
          insurers: ["Example Health"],
          cpt_codes: ["99213"],
          page: "2",
          balance: 15,
        }),
        record({
          invoice_number: "INV-200",
          provider: "Beta Pharmacy",
          insurers: [],
          third_parties: ["Caremark"],
          cpt_codes: [],
          description: "Pharmacy ledger",
          total_charges: 250,
          balance: 0,
          page: "6-7",
        }),
        record({
          invoice_number: null,
          provider: "Gamma Hospital",
          cpt_codes: [],
          total_charges: null,
          balance: null,
          page: "9",
        }),
      ],
      flagged: [flag({ row: 1, reason: "Column mapping unclear" })],
    }),
  ]);

  it("matches text across file, provider, invoice, payer, CPT, description, and page", () => {
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "source-a" }),
    ).toHaveLength(3);
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "beta pharmacy" }),
    ).toHaveLength(1);
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "INV-100" }),
    ).toHaveLength(1);
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "caremark" }),
    ).toHaveLength(1);
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "99213" }),
    ).toHaveLength(1);
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "ledger" }),
    ).toHaveLength(1);
    expect(filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, query: "6-7" })).toHaveLength(1);
  });

  it("combines provider and invoice dropdown filters", () => {
    const filtered = filterReportRows(rows, {
      ...DEFAULT_REPORT_FILTERS,
      provider: "Gamma Hospital",
      invoice: MISSING_INVOICE_VALUE,
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.provider).toBe("Gamma Hospital");
  });

  it("combines review and financial filters", () => {
    expect(
      filterReportRows(rows, {
        ...DEFAULT_REPORT_FILTERS,
        review: "needs_review",
        financial: "has_charges",
      }).map((row) => row.provider),
    ).toEqual(["Beta Pharmacy"]);

    expect(
      filterReportRows(rows, {
        ...DEFAULT_REPORT_FILTERS,
        review: "clean",
        financial: "has_balance",
      }).map((row) => row.provider),
    ).toEqual(["Alpha Clinic"]);
  });
});

describe("parseTreatmentDate", () => {
  it("reads ISO and US formats and the start of a range", () => {
    expect(parseTreatmentDate("2017-03-16")).toBe("2017-03-16");
    expect(parseTreatmentDate("03/16/2017")).toBe("2017-03-16");
    expect(parseTreatmentDate("3/6/2017")).toBe("2017-03-06");
    expect(parseTreatmentDate("03/16/2017 – 03/20/2017")).toBe("2017-03-16");
    expect(parseTreatmentDate("3-16-17")).toBe("2017-03-16");
  });

  it("returns null when no date is present", () => {
    expect(parseTreatmentDate("Various")).toBeNull();
    expect(parseTreatmentDate("")).toBeNull();
    expect(parseTreatmentDate(null)).toBeNull();
  });

  it("rejects out-of-range and garbage digit runs instead of inventing dates", () => {
    expect(parseTreatmentDate("Invoice 88-77-6655")).toBeNull();
    expect(parseTreatmentDate("13/45/2017")).toBeNull(); // month 13, day 45
    expect(parseTreatmentDate("02/30/2018")).toBeNull(); // Feb 30 doesn't exist
    expect(parseTreatmentDate("2020-99-99")).toBeNull();
    expect(parseTreatmentDate("2017-3-6")).toBe("2017-03-06"); // single-digit parts ok
  });
});

describe("parseTreatmentDateRange", () => {
  it("returns first and last valid dates of a range", () => {
    expect(parseTreatmentDateRange("03/16/2017 – 03/20/2017")).toEqual({
      start: "2017-03-16",
      end: "2017-03-20",
    });
  });

  it("collapses a single date to start === end", () => {
    expect(parseTreatmentDateRange("01/01/2026")).toEqual({
      start: "2026-01-01",
      end: "2026-01-01",
    });
  });

  it("returns nulls when undated", () => {
    expect(parseTreatmentDateRange("Various")).toEqual({ start: null, end: null });
  });
});

describe("filterReportRows — payer and date range", () => {
  const rows = flattenReportRows([
    job({
      records: [
        record({ provider: "Alpha", insurers: ["Blue Cross"], treatment_date: "01/10/2026" }),
        record({ provider: "Beta", insurers: [], third_parties: ["Caremark"], treatment_date: "06/15/2026" }),
        record({ provider: "Gamma", insurers: ["Aetna"], treatment_date: "Various" }),
      ],
    }),
  ]);

  it("filters by payer across insurers and third parties", () => {
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, payer: "Caremark" }).map((r) => r.provider),
    ).toEqual(["Beta"]);
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, payer: "Blue Cross" }).map((r) => r.provider),
    ).toEqual(["Alpha"]);
  });

  it("filters by date range and drops rows with no parseable date", () => {
    expect(
      filterReportRows(rows, {
        ...DEFAULT_REPORT_FILTERS,
        dateFrom: "2026-01-01",
        dateTo: "2026-03-31",
      }).map((r) => r.provider),
    ).toEqual(["Alpha"]);

    // An open-ended lower bound still excludes the undated "Various" row.
    expect(
      filterReportRows(rows, { ...DEFAULT_REPORT_FILTERS, dateFrom: "2026-01-01" }).map((r) => r.provider),
    ).toEqual(["Alpha", "Beta"]);
  });

  it("exposes payer options for the dropdown", () => {
    expect(reportFilterOptions(rows).payers).toEqual(["Aetna", "Blue Cross", "Caremark"]);
  });

  it("keeps a multi-day range that overlaps the window but starts before it", () => {
    const ranged = flattenReportRows([
      job({
        records: [
          record({ provider: "Spans-in", treatment_date: "01/10/2026 – 02/15/2026" }),
          record({ provider: "Spans-out", treatment_date: "06/01/2026 – 06/30/2026" }),
        ],
      }),
    ]);

    // Window starts mid-range for "Spans-in": a start-only filter would have
    // wrongly dropped it; the overlap filter keeps it.
    expect(
      filterReportRows(ranged, {
        ...DEFAULT_REPORT_FILTERS,
        dateFrom: "2026-02-01",
        dateTo: "2026-02-28",
      }).map((r) => r.provider),
    ).toEqual(["Spans-in"]);
  });
});

describe("summarizeReportRows", () => {
  it("aggregates totals across filtered rows", () => {
    const rows = flattenReportRows([
      job({
        records: [
          record({ total_charges: 100, ins_paid: 60, adjustment: 20, payments: 5, balance: 15 }),
          record({ total_charges: 200, ins_paid: null, adjustment: 10, payments: 25, balance: 0 }),
        ],
      }),
    ]);

    expect(summarizeReportRows(rows)).toEqual({
      records: 2,
      totalCharges: 300,
      insPaid: 60,
      adjustment: 30,
      payments: 30,
      balance: 15,
    });
  });
});
