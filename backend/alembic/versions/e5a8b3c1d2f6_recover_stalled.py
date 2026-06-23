"""crash recovery: recover_stalled_jobs() SECURITY DEFINER function

A job that reaches 'processing' never silently regresses. But if the worker
holding it crashes, the row would be stranded in 'processing' forever. This
function recovers such rows — and, like claim, it must see across owners, so it
is SECURITY DEFINER (owner-run, RLS-exempt) with EXECUTE granted only to the app
role.

Recovery is time-gated and logged, not silent: a job is "stalled" only once it
has been in 'processing' longer than ``timeout_minutes`` (well beyond the seconds
a real job takes). A stalled job with retries left goes back to 'pending' (a
worker re-claims it, which bumps attempts); once attempts are exhausted it is
marked 'failed' instead, so a job that crashes a worker every time cannot loop
forever.

Revision ID: e5a8b3c1d2f6
Revises: d4f7a1b2c3e5
Create Date: 2026-06-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5a8b3c1d2f6"
down_revision: Union[str, Sequence[str], None] = "d4f7a1b2c3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "billing_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION recover_stalled_jobs(
            timeout_minutes integer,
            max_attempts integer
        )
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            affected integer;
        BEGIN
            UPDATE jobs
               SET status = CASE WHEN attempts >= max_attempts
                                 THEN 'failed' ELSE 'pending' END,
                   error = CASE WHEN attempts >= max_attempts
                                THEN 'Recovered after worker stall; max attempts ('
                                     || max_attempts || ') exhausted'
                                ELSE error END,
                   completed_at = CASE WHEN attempts >= max_attempts
                                       THEN now() ELSE completed_at END,
                   updated_at = now()
             WHERE status = 'processing'
               AND started_at < now() - make_interval(mins => timeout_minutes);
            GET DIAGNOSTICS affected = ROW_COUNT;
            RETURN affected;
        END;
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION recover_stalled_jobs(integer, integer) FROM PUBLIC;"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION recover_stalled_jobs(integer, integer) TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS recover_stalled_jobs(integer, integer);")
