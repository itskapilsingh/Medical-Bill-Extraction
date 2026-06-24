"""performance indexes for the job list and the worker queue

Two hot paths were doing more work than they needed to:

- ``GET /jobs`` lists a user's jobs newest-first (now paginated). RLS rewrites it
  to ``owner_id = current_setting(...) ORDER BY created_at DESC``, so a composite
  ``(owner_id, created_at DESC)`` index turns it into an index range scan instead
  of a per-owner sort.
- ``claim_next_job()`` repeatedly runs ``WHERE status = 'pending' ORDER BY
  created_at`` under every worker poll. A partial index on the pending rows keeps
  that lookup cheap as the completed history grows (the pending set stays small).

Both are pure read-path optimizations; no data or policy changes.

Revision ID: f6b9c2d3e4a7
Revises: e5a8b3c1d2f6
Create Date: 2026-06-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f6b9c2d3e4a7"
down_revision: Union[str, Sequence[str], None] = "e5a8b3c1d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_owner_created "
        "ON jobs (owner_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_pending_created "
        "ON jobs (created_at) WHERE status = 'pending';"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_pending_created;")
    op.execute("DROP INDEX IF EXISTS idx_jobs_owner_created;")
