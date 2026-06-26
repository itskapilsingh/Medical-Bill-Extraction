import { describe, expect, it } from "vitest";

import { groupRecordsByInvoice, invoiceLabel } from "@/lib/invoices";
import type { BillingRecord } from "@/lib/types";

function record(invoiceNumber: string | null, provider: string): BillingRecord {
  return {
    invoice_number: invoiceNumber,
    treatment_date: "01/01/2026",
    cpt_codes: [],
    description: null,
    provider,
    insurers: [],
    third_parties: [],
    total_charges: null,
    ins_paid: null,
    adjustment: null,
    payments: null,
    balance: null,
    page: "1",
  };
}

describe("invoiceLabel", () => {
  it("labels known and missing invoice numbers", () => {
    expect(invoiceLabel("INV-100")).toBe("Invoice INV-100");
    expect(invoiceLabel(null)).toBe("Invoice not found");
  });
});

describe("groupRecordsByInvoice", () => {
  it("keeps records from the same invoice together in first-seen order", () => {
    const groups = groupRecordsByInvoice([
      record("INV-100", "A"),
      record("INV-200", "B"),
      record("INV-100", "C"),
    ]);

    expect(groups.map((group) => group.label)).toEqual([
      "Invoice INV-100",
      "Invoice INV-200",
    ]);
    expect(groups[0]?.records.map((r) => r.provider)).toEqual(["A", "C"]);
    expect(groups[1]?.records.map((r) => r.provider)).toEqual(["B"]);
  });

  it("groups blank or missing invoice numbers under a visible fallback", () => {
    const groups = groupRecordsByInvoice([
      record(null, "A"),
      record("   ", "B"),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.label).toBe("Invoice not found");
    expect(groups[0]?.records).toHaveLength(2);
  });
});
