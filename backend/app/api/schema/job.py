"""API response envelope for jobs.

This is the shape documented in ``docs/schema.md`` and returned verbatim by the
``/jobs`` routes (``GET /jobs``, ``GET /jobs/active``, ``GET /jobs/{id}``, and
``POST /jobs``). Metrics are ``null`` until the worker fills them in.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.extraction import BillingRecord, FlaggedRecord


class TokenUsage(BaseModel):
    """LLM token counts for a job. Providers may add sub-fields; we keep extras."""

    model_config = {"extra": "allow"}

    input: int = 0
    output: int = 0
    total: int = 0


class JobResponse(BaseModel):
    """One job as returned by the API."""

    job_id: str
    status: str
    pdf_path: str
    records: list[BillingRecord] = Field(default_factory=list)
    flagged: list[FlaggedRecord] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None
    token_usage: TokenUsage | None = None
    cost_usd: float | None = None
    processing_duration_seconds: float | None = None
    error: str | None = None

    @classmethod
    def from_job(cls, job: dict[str, Any]) -> "JobResponse":
        """Map a JobDAO dict to the public envelope.

        ``records`` / ``flagged`` are pulled out of the stored ``result`` JSON so
        the worker's persisted shape and the API contract are decoupled: the DB
        row keeps the whole extraction result, the API surfaces the documented
        fields.
        """
        result = job.get("result") or {}
        return cls(
            job_id=job["id"],
            status=job["status"],
            pdf_path=job["pdf_path"],
            records=result.get("records", []),
            flagged=result.get("flagged", []),
            created_at=job["created_at"],
            completed_at=job.get("completed_at"),
            token_usage=job.get("token_usage"),
            cost_usd=job.get("cost_usd"),
            processing_duration_seconds=job.get("processing_duration_seconds"),
            error=job.get("error"),
        )
