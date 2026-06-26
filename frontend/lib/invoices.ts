import type { BillingRecord } from "@/lib/types";

export interface InvoiceRecordGroup {
  invoiceNumber: string | null;
  label: string;
  records: BillingRecord[];
}

function normalizeInvoiceNumber(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function invoiceLabel(invoiceNumber: string | null): string {
  return invoiceNumber ? `Invoice ${invoiceNumber}` : "Invoice not found";
}

export function groupRecordsByInvoice(records: BillingRecord[]): InvoiceRecordGroup[] {
  const groups = new Map<string, InvoiceRecordGroup>();

  for (const record of records) {
    const invoiceNumber = normalizeInvoiceNumber(record.invoice_number);
    const key = invoiceNumber ?? "__missing_invoice__";
    const existing = groups.get(key);
    if (existing) {
      existing.records.push(record);
      continue;
    }
    groups.set(key, {
      invoiceNumber,
      label: invoiceLabel(invoiceNumber),
      records: [record],
    });
  }

  return Array.from(groups.values());
}
