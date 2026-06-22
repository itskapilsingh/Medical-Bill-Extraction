"""Heuristic page classification used by the agent's outline tool.

These billing PDFs interleave the real billing data with noise — cover sheets,
records-certification forms, lab reports, prescriptions, and clinical notes. A
cheap, deterministic guess at each page's kind lets the agent jump straight to
the billing pages and skip the rest, instead of paying tokens to read (and reason
about) every page. The guess is advisory: the agent still reads the page text and
decides. It is intentionally simple string matching, not a model.
"""

from __future__ import annotations

# Kinds the agent should EXTRACT from.
BILLING_KINDS = {"billing_ledger", "pharmacy_ledger"}

# Kinds the agent should SKIP.
NOISE_KINDS = {"cover", "certification", "lab_report", "prescription", "empty"}


def classify_page(text: str) -> str:
    """Return a best-guess kind for a page's extracted text.

    One of: cover, certification, lab_report, pharmacy_ledger, billing_ledger,
    prescription, empty, other. Order matters — billing/pharmacy signals are
    checked before prescription, because pharmacy ledgers also contain a
    "PRESCRIBER" column.
    """
    if not text or not text.strip():
        return "empty"
    t = text.lower()

    if "records pertaining to" in t or "records custodian" in t:
        return "cover"
    if "certification of records" in t:
        return "certification"
    if "laboratory report" in t or ("test name" in t and "reference range" in t):
        return "lab_report"
    # Pharmacy fill ledger: RX numbers, fill dates, NDC codes, third-party payers.
    if "rx #" in t or "fill date" in t or "3rd party" in t or ("ndc" in t and "copay" in t):
        return "pharmacy_ledger"
    # Medical billing ledger: claim groups with charges/adjustments/totals.
    if (
        "billing summary" in t
        or "claim id" in t
        or "claim total" in t
        or "contractual adjustment" in t
    ):
        return "billing_ledger"
    if "clinical note" in t or "prescriber:" in t or ("diagnosis:" in t and "npi:" in t):
        return "prescription"
    return "other"
