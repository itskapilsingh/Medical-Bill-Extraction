from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.dao.models.base import TimestampBase


class Job(TimestampBase):
    """One extraction job in the queue.

    ``owner_id`` is the Better Auth user id of the uploader. It is the column
    every Row-Level Security policy on this table keys on, so it is non-null and
    indexed. Application code also filters by it, but RLS is what makes a missing
    filter non-fatal.
    """

    __tablename__ = "jobs"

    __table_args__ = (
        Index("idx_jobs_owner_id", "owner_id"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created_at", "created_at"),
        Index(
            "idx_jobs_status_created",
            "status",
            "created_at",
            postgresql_where="status = 'pending'",
        ),
        # Content-based cache lookups are always scoped to a single owner, so the
        # fingerprint is only ever meaningful together with owner_id.
        Index("idx_jobs_owner_hash", "owner_id", "content_hash"),
    )

    # The database generates the id (gen_random_uuid()::text, set in the initial
    # migration). Declaring the server_default here tells SQLAlchemy to fetch the
    # generated value back via RETURNING on INSERT.
    id: Mapped[str] = mapped_column(
        String, primary_key=True, server_default=text("gen_random_uuid()::text")
    )
    # FK to "user"(id) is enforced in the database (see the jobs RLS migration).
    # It is intentionally NOT declared as an ORM ForeignKey: the Better Auth
    # tables are managed as raw-SQL migrations, not ORM models, so a string
    # ForeignKey("user.id") could not be resolved against Base.metadata at flush
    # time. Postgres still guarantees referential integrity and ON DELETE CASCADE.
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    pdf_filename: Mapped[str] = mapped_column(String, nullable=False)
    pdf_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")

    # SHA-256 of the uploaded file's bytes. Drives per-user result caching (M3).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-job metrics (required on every job payload from M2). JSON null until known.
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_duration_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    # Retry bookkeeping (M3). Number of times a worker has attempted this job.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
