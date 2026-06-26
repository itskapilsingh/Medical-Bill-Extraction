# Medical Billing Domain Reference

This document gives you the domain knowledge needed to build the extraction system.
Read it fully before writing any code. The edge cases are not edge cases in practice —
they appear regularly in real billing documents.

---

## 1. What a Medical Bill Is

A medical bill is a record of services rendered, charges billed, adjustments applied,
and amounts owed. It is produced by a provider (hospital, clinic, physician group,
or pharmacy) and submitted to one or more insurers and/or the patient.

The same patient encounter can generate multiple document types in a single PDF:
a summary page, an itemized line-item table, and sometimes a standardized claim form.
Your agent needs to identify which document type it is looking at and apply the
appropriate extraction rules for each.

**The goal is not to extract every itemized line.** The goal is to produce one output
row per distinct provider episode — a high-level billing summary that lets an attorney
quickly understand the financial picture without reading every page.

Read the samples with their corresponding ground truth in the `data` folder to understand the different document types and how to extract the data from them. Spend some time on this to understand the intent of the extraction.

---

## 2. Output Record

Each extracted record corresponds to one **billing episode** — typically one provider,
one claim group, or one pharmacy fill range.

| Field | Description |
|---|---|
| **Invoice Number** | Invoice, statement, bill, claim, or account identifier that groups records inside the PDF. If a single PDF contains multiple invoices, preserve the exact visible identifier on each row so records can be saved and reviewed invoice-wise. Leave blank/null when no invoice-like identifier is shown; do not use RX/NDC/item codes as invoice numbers. |
| **Treatment Date** | Date or date range of the service or prescription fill. Use the treatment/service date, not the payment or processing date. For pharmacy records summarized over a range of fills, use the full date range (e.g., `10/10/2025 – 01/26/2026`). |
| **CPT Code** | Procedure code(s) for medical records. A single episode may carry multiple CPT codes — list all of them. For pharmacy records, leave blank. Do not substitute NDC codes, Rx numbers, or transaction codes for CPT codes. |
| **Description** | Brief description of the procedure, service, or medication category. Can be inferred from a summary page or general breakdown if CPT codes are absent. |
| **Provider** | The healthcare practice, clinic, hospital, or facility that rendered the service — not an individual clinician. For pharmacy records, the pharmacy name. Use the practice/facility name even when individual physician names appear on service lines. |
| **Insurer** | The insurance company (or companies) involved. On documents, roles like primary (`PRI`), secondary (`SEC`), and supplemental (`SUP`) help you read the table. In **structured output**, list each distinct insurer **by name only** (see schema) — do not attach dollar amounts per insurer; use **Ins. Paid** for the combined insurer-side payment on that row. Leave blank if no insurer is clearly identified. If a payment was made but the payer is unknown, you may use the label `"Insurance Payment"`. |
| **Third Party** | Any non-insurance, non-patient payer — PBMs, workers' comp administrators, law firms, discount programs. In **structured output**, list **names only** (see schema), separate from insurers. Do not merge third-party and insurer payments into one mental bucket while reading the document. |
| **Total Charges** | Gross amount billed before any adjustments or payments. When not explicitly stated, total charges = sum of all payment columns. When a summary page is present, always use it rather than summing itemized rows. |
| **Ins. Paid** | Amount the insurer paid. Leave blank if the insurer cannot be identified. |
| **Adjustment** | Write-offs, contractual adjustments, discounts. Multiple adjustment types can be grouped into a single value. |
| **Payments** | Amount paid out-of-pocket by the patient. If a payment exists but the payer cannot be determined with certainty, label it as a generic `"Payment"` rather than attributing it to a specific party. |
| **Balance** | Remaining balance after charges, payments, and adjustments. Usually zero for completed claims. If unresolved, show it and leave unattributed portions open rather than guessing. |
| **Page** | Source PDF page number(s) where this record appears. Required — attorneys use this to locate the original document. |

---

## 3. Document Types

### 3.1 Medical Billing Ledger

The primary document type. Contains claim groups with charges, payments, adjustments,
balance, insurer information, and treatment dates.

**Rule:** When both a HICFA form and a billing ledger are present for the same episode,
the billing ledger is the source of truth. Use the HICFA only as a fallback.

### 3.2 Pharmacy Records

Key differences from medical billing:

- No CPT codes — leave CPT field blank. Rx numbers are internal tracking identifiers.
- Provider = pharmacy name. The prescribing doctor is not surfaced in the output.
- May involve PBMs (Pharmacy Benefit Managers) such as Caremark, OptumRx, Medco — treat as third party.
- Date of service = fill date (date the prescription was dispensed).
- When a summary page is present, use it. Do not re-aggregate itemized rows.

### 3.3 Scanned Pages and Embedded Screenshots

Some billing packets contain image-only scans or screenshots from billing and
pharmacy systems. Treat the visible page image as the source document: extract the
same billing episodes, invoice numbers, totals, payer names, and page references
you would extract from text. If a value is visually present but unreadable, flag
that field instead of guessing. If a screenshot is only software chrome or a
non-billing page, ignore it.

---

## 4. Custodian vs. Provider

The **custodian** is the entity that holds and certifies the records. The **provider**
is the practice, clinic, hospital, or facility that rendered care.

They are often the same entity. They can differ — a records management company may be
the custodian while the actual records originate from one or more separate treating
facilities.

**Always use the healthcare provider (not the custodian) for the Provider field.**
The custodian is not surfaced in the output.

---

## 5. Payment Attribution Rules

### Insurer vs. Third Party

These are not the same and must never be combined:

- **Insurer**: A health insurance company — Medicare, Medicaid, Blue Cross Blue Shield,
  Aetna, Molina Healthcare, etc.
- **Third Party**: Any other non-patient entity making a payment — PBMs, workers' comp
  administrators, law firms, prescription discount programs, any entity labeled "TP"
  in the source document.

### TP / PT Column Conventions

Some pharmacy billing systems use:
- `TP Paid` → Third Party payment (maps to Third Party field)
- `PT Paid` → Patient payment (maps to Payments field)

In these cases: Total Charges = TP Paid + PT Paid unless a summary page says otherwise.
This is an assumption — flag it.

### When the Payer is Unknown

If a payment exists but the payer cannot be determined:
1. Do not guess.
2. Log the amount under a generic `"Payment"` label.
3. Leave the Insurer field blank — do not write "N/A" or "Unknown."
4. Show the resulting balance if one exists.

Exception: if the document lists only one responsible party (the patient) and no
insurance information exists anywhere, attributing the payment to the patient is
acceptable — but still flag it.

---

## 6. Summary Pages vs. Itemized Rows

When a document contains both itemized line items and a summary page:

- Always use the summary page as the basis for the output record.
- Do not re-sum itemized rows unless there is no summary page.
- If a summary page is absent, calculate totals from itemized rows.

---

## 7. Flagging Rules

A record should be flagged for manual review if any of the following are true:

- 4 or more of the 5 core financial fields (Total Charges, Ins. Paid, Adjustment,
  Payments, Balance) cannot be identified or are unresolvable
- A payment exists but it is genuinely impossible to determine who paid it
- The total charge cannot be identified at all
- Column-to-value mapping is ambiguous and cannot be resolved from context

Use the following severity levels when flagging:

- `high` — financial totals are missing or completely unresolvable; document-level failure.
- `medium` — some data is available but specific fields are uncertain.
- `low` — minor ambiguity; a single field is unclear but the record is otherwise complete.

**Flagged records must appear in your output** — do not silently drop them.
A flagged record with blank financial fields is a valid output. A confidently wrong
record is not.

---

## 8. General Principles

1. Prefer summary pages over itemized rows.
2. Leave blank rather than guess — never write "N/A" or "Unknown."
3. Never combine insurer and third-party payments.
4. Adjustments can be grouped; payments cannot.
5. Use treatment dates, not payment dates.
6. A zero balance confirms a record is complete.
7. Each distinct provider episode = one output row.
8. Pharmacy records do not use CPT codes.
9. Flag early — uncertain records should be surfaced, not suppressed.

---

## 9. Key Terminology

| Term | Meaning |
|---|---|
| Custodian | Entity that holds and certifies the records. May differ from provider. |
| Provider | Entity that rendered care or dispensed medication. |
| PBM | Pharmacy Benefit Manager — third party that processes pharmacy payments (e.g., Caremark, OptumRx, Medco). |
| TP | Third Party — a non-insurance, non-patient payer. In pharmacy software, often "TP Total." |
| PT | Patient — in pharmacy software, "PT Pay" = patient payment. |
| Adjustment / Write-off | Reduction in billed amount, often due to contractual rates between provider and insurer. |
| PRI / SEC / SUP | Insurer role tags: Primary, Secondary, Supplemental. A single episode can have multiple. |
| Fill Date | Date a prescription was dispensed. Equivalent to treatment date for pharmacy records. |
| Date Written | Date the prescription was written by the prescribing physician. |
| Responsible Party | The individual (usually the patient) legally responsible for the bill. |
| Purge Data | Records from inactive/closed sources retained as archives. Often incomplete. |
