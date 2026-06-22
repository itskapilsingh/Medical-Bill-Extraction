"""worker queue: claim_next_job() SECURITY DEFINER function

The worker connects as the RLS-enforced billing_app role, which (correctly)
cannot see other users' jobs. But the queue is shared: a worker must be able to
pull the next pending job regardless of who owns it. This function is the single,
minimal, audited place where that cross-user read happens.

- SECURITY DEFINER + owned by the schema owner (billing) → runs RLS-exempt
  (RLS is ENABLE, not FORCE, so the owner is exempt). The app role gets only
  EXECUTE on this one function; it still cannot SELECT across users directly.
- FOR UPDATE SKIP LOCKED → two concurrent workers never claim the same row: the
  first locks it, the second skips to the next.
- SET search_path = public → standard hardening for SECURITY DEFINER.

The worker reads owner_id off the returned row and then writes the result under
that owner's identity (acting_as), so the *write* is still RLS-scoped — only the
claim is privileged.

Revision ID: d4f7a1b2c3e5
Revises: c3d5f7b91a22
Create Date: 2026-06-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4f7a1b2c3e5"
down_revision: Union[str, Sequence[str], None] = "c3d5f7b91a22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "billing_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION claim_next_job()
        RETURNS SETOF jobs
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            claimed jobs;
        BEGIN
            SELECT * INTO claimed
            FROM jobs
            WHERE status = 'pending'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1;

            IF NOT FOUND THEN
                RETURN;
            END IF;

            UPDATE jobs
               SET status = 'processing',
                   started_at = now(),
                   attempts = attempts + 1,
                   updated_at = now()
             WHERE id = claimed.id;

            claimed.status := 'processing';
            claimed.started_at := now();
            claimed.attempts := claimed.attempts + 1;
            RETURN NEXT claimed;
        END;
        $$;
        """
    )
    # Only the application role may run it; nobody else.
    op.execute("REVOKE ALL ON FUNCTION claim_next_job() FROM PUBLIC;")
    op.execute(f"GRANT EXECUTE ON FUNCTION claim_next_job() TO {APP_ROLE};")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS claim_next_job();")
