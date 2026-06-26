"""DB-level in-flight dedup + summary aggregate index

Two read-path/write-path hardenings:

- A PARTIAL UNIQUE index makes "one active job per (owner, content) " a database
  invariant instead of an application read-then-write. The existing
  find_active_duplicate() check still short-circuits the common case, but if two
  identical uploads from the same user race past it before either commits, the
  unique index rejects the second INSERT and the service coalesces onto the
  winner — so the worker never runs (and the model never bills) the same document
  twice. Scoped to pending/processing only, so re-uploading after a job completes
  is still allowed (it hits the completed-result cache instead).

- A partial index on completed jobs backs GET /jobs/summary's financial
  aggregate, which only unnests completed jobs' records.

Revision ID: b7d1e2f3a4c5
Revises: a6f2c9d8e3b1
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7d1e2f3a4c5"
down_revision: Union[str, Sequence[str], None] = "a6f2c9d8e3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_active_dedup "
        "ON jobs (owner_id, content_hash) "
        "WHERE content_hash IS NOT NULL AND status IN ('pending', 'processing');"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_owner_completed "
        "ON jobs (owner_id) WHERE status = 'completed';"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_owner_completed;")
    op.execute("DROP INDEX IF EXISTS idx_jobs_active_dedup;")
