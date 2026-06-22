"""Extraction output types.

Field semantics are defined by Pydantic ``Field(..., description=...)`` on each
attribute. ``docs/schema.md`` defers to this module for ``BillingRecord`` and
``FlaggedRecord``.
"""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]


class BillingRecord(BaseModel):
    """One billing episode row in the extraction result."""

    treatment_date: str = Field(
        description=(
            "Date or date range for the service or fill, as shown on the bill "
            "(not payment or posted dates). Do not normalize format — preserve how it appears."
        ),
    )
    cpt_codes: list[str] = Field(
        default_factory=list,
        description=(
            "Procedure codes for medical rows; empty list for pharmacy. "
            "Do not substitute NDC or Rx numbers for CPT."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Brief procedure, service, or medication-category description.",
    )
    provider: str = Field(
        description=(
            "Practice, facility, hospital, or pharmacy name — not an individual clinician."
        ),
    )
    insurers: list[str] = Field(
        default_factory=list,
        description=(
            "Insurer names only, one string each. Use an empty list if none; "
            "aggregate insurer paid amount is ``ins_paid``."
        ),
    )
    third_parties: list[str] = Field(
        default_factory=list,
        description=(
            "Non-insurer payers (PBMs, discount programs, workers' comp, etc.), "
            "names only. Empty list if none."
        ),
    )
    total_charges: float | None = Field(
        default=None,
        description="Gross billed charges before adjustments and payments.",
    )
    ins_paid: float | None = Field(
        default=None,
        description="Total amount paid by insurance for this episode.",
    )
    adjustment: float | None = Field(
        default=None,
        description="Write-offs, contractual adjustments, discounts (combined if multiple).",
    )
    payments: float | None = Field(
        default=None,
        description="Out-of-pocket patient payments attributed to this episode.",
    )
    balance: float | None = Field(
        default=None,
        description="Remaining balance after charges, payments, and adjustments.",
    )
    page: str = Field(
        description='Source page(s) as a string, e.g. "12" or "12-14".',
    )


class FlaggedRecord(BaseModel):
    """Issue requiring manual review; may or may not tie to a specific output row."""

    row: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Zero-based index into the job's ``records`` array for the billing row this "
            "flag concerns. Use ``null`` when the problem does not correspond to any row "
            "emitted in ``records`` (e.g. document-level ambiguity, skipped section)."
        ),
    )
    fields: list[str] = Field(
        default_factory=list,
        description=(
            "Names of ``BillingRecord`` fields affected by this issue (e.g. "
            "``total_charges``, ``ins_paid``). Empty if not field-specific."
        ),
    )
    reason: str = Field(
        description="Short explanation of why manual review is needed.",
    )
    page: str = Field(
        description='Source page(s) as a string, e.g. "7" or "7-9".',
    )
    severity: Severity = Field(
        description='Severity: "low", "medium", or "high" — see docs/domain.md flagging rules.',
    )


class ExtractionOutput(BaseModel):
    """The agent's final structured output for one document.

    Persisted as the job's ``result`` JSON and surfaced (as ``records`` /
    ``flagged``) by the API envelope described in ``docs/schema.md``.
    """

    records: list[BillingRecord] = Field(
        default_factory=list,
        description="One row per distinct provider/claim/fill episode.",
    )
    flagged: list[FlaggedRecord] = Field(
        default_factory=list,
        description="Records or issues that need manual review.",
    )
