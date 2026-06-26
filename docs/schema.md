# Output Schema

This document describes extraction output and the job API envelope. **Field meanings for**
**`BillingRecord` and `FlaggedRecord` are defined in code** — each attribute uses Pydantic
`Field(..., description=...)` in
[`backend/app/models/extraction.py`](../backend/app/models/extraction.py). Read that file (or generate /
inspect the JSON Schema from the models) for the authoritative descriptions.

Output that does not conform scores zero for that record.

---

## Top-Level Response: `ExtractionResult`

Every call to `GET /jobs/{job_id}` for a completed job follows this shape. The same
envelope is used for `GET /jobs` and `GET /jobs/active`; use `null` for metrics that are
not known yet.

```json
{
  "job_id": "uuid",
  "status": "completed",
  "pdf_path": "/app/pdfs/filename.pdf",
  "records": [ ...BillingRecord... ],
  "flagged": [ ...FlaggedRecord... ],
  "created_at": "ISO8601",
  "completed_at": "ISO8601",
  "token_usage": { "input": 12000, "output": 3400, "total": 15400 },
  "cost_usd": 0.12,
  "processing_duration_seconds": 84.5
}
```

| Field | Notes |
|---|---|
| `job_id` | Assigned at creation (UUID string). |
| `status` | `pending`, `processing`, `completed`, `failed`, or `cancelled`. |
| `pdf_path` | Path to the PDF on the volume. |
| `records` | Extracted billing rows. |
| `flagged` | Rows needing manual review. |
| `created_at` | ISO8601. |
| `completed_at` | ISO8601 when finished, or null. |
| `token_usage` | LLM token counts for this job (at minimum: `input`, `output`, `total`). Providers may return extra sub-fields such as reasoning tokens or cached input tokens; store what your provider returns. Null until the worker finishes. |
| `cost_usd` | Estimated API spend in USD; null until known. |
| `processing_duration_seconds` | Wall time for this job; null until finished. |
| `error` | Human-readable failure description; only present when `status` is `failed`. |

These job-level fields should match what you store on the job row and return from the API.

---

## `BillingRecord`

One output row per provider episode. **Each field’s meaning is the Pydantic**
`Field(..., description=...)` **on that attribute in**
[`BillingRecord`](../backend/app/models/extraction.py).

```json
{
  "invoice_number": "INV-10422",
  "treatment_date": "03/16/2017 – 03/20/2017",
  "cpt_codes": ["99221", "99456"],
  "description": "Inpatient hospital services",
  "provider": "NYU Langone Orthopedics",
  "insurers": ["Blue Cross Blue Shield"],
  "third_parties": ["Caremark"],
  "total_charges": 1850.00,
  "ins_paid": 1240.00,
  "adjustment": 565.00,
  "payments": 45.00,
  "balance": 0.00,
  "page": "12-14"
}
```

---

## `FlaggedRecord`

Material that could not be extracted with enough confidence must appear here, not be
dropped. **Each field’s meaning is the Pydantic** `Field(..., description=...)` **on**
[`FlaggedRecord`](../backend/app/models/extraction.py).

```json
{
  "row": 2,
  "fields": ["ins_paid", "balance"],
  "reason": "Column-to-value mapping ambiguous — OCR misalignment on header row",
  "page": "7-9",
  "severity": "high"
}
```

Use `"row": null` when the flag does not point at a specific row in `records` (nothing new added to the output for this issue, or the issue is document-wide).

---

## Failed Job Response

If the worker failed to process a job, `GET /jobs/{job_id}` returns:

```json
{
  "job_id": "uuid",
  "status": "failed",
  "error": "Descriptive error message",
  "records": [],
  "flagged": [],
  "created_at": "ISO8601",
  "completed_at": "ISO8601",
  "token_usage": { "input": 8000, "output": 400, "total": 8400 },
  "cost_usd": 0.07,
  "processing_duration_seconds": 32.1
}
```

Include `token_usage`, `cost_usd`, and `processing_duration_seconds` when known; otherwise `null`.

A failed job is not the same as a job that produced flagged records. A failed job
means the worker itself threw an unhandled error. Flagged records are an expected,
valid output.

---

## Null vs. Blank vs. Missing

| Situation | What to output |
|---|---|
| Field is present in the document and has a value | The value |
| Field is explicitly present but zero | `0.0` (not null) |
| Field is not present in the document | `null` |
| Field cannot be determined due to ambiguity | `null` + flag the record |
| Field does not apply to this document type | `null` (e.g., `cpt_codes` for pharmacy = `[]`) |

Never output `"N/A"`, `"Unknown"`, `"n/a"`, or empty string `""` for missing fields.
Use `null` or empty list as appropriate.
