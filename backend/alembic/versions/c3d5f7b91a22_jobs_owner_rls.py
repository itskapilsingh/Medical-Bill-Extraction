"""add job ownership + metrics and enforce Row-Level Security on jobs

This is the heart of the isolation guarantee. After this migration:

- every job carries an ``owner_id`` (the Better Auth user id), FK to ``"user"``;
- RLS is ENABLED on ``jobs`` with per-command policies that compare ``owner_id``
  to ``current_setting('app.user_id')`` — the GUC the app stamps onto each
  transaction;
- the app role (``billing_app``) is granted DML on ``jobs`` but, being a
  non-owner, non-BYPASSRLS role, can only ever touch rows the policies admit.

We ENABLE (not FORCE) RLS deliberately: the schema owner stays exempt so that
the single, minimal SECURITY DEFINER queue-claim function added in M2 — and only
that function — can pull pending jobs across owners. The app role is never the
owner, so it is always subject to the policies.

Revision ID: c3d5f7b91a22
Revises: b2c4e6a80f11
Create Date: 2026-06-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d5f7b91a22"
down_revision: Union[str, Sequence[str], None] = "b2c4e6a80f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "billing_app"
USER_ID_SETTING = "app.user_id"


def upgrade() -> None:
    # --- ownership + new columns ------------------------------------------------
    op.add_column("jobs", sa.Column("owner_id", sa.String(), nullable=False))
    op.add_column("jobs", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("jobs", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("processing_duration_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_foreign_key(
        "fk_jobs_owner_id_user",
        source_table="jobs",
        referent_table="user",
        local_cols=["owner_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_jobs_owner_id", "jobs", ["owner_id"])
    op.create_index("idx_jobs_owner_hash", "jobs", ["owner_id", "content_hash"])

    # --- privileges for the RLS-enforced app role -------------------------------
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE jobs TO {APP_ROLE};")

    # --- enable RLS + per-command policies --------------------------------------
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY jobs_select ON jobs FOR SELECT
            USING (owner_id = current_setting('{USER_ID_SETTING}', true));
        """
    )
    op.execute(
        f"""
        CREATE POLICY jobs_insert ON jobs FOR INSERT
            WITH CHECK (owner_id = current_setting('{USER_ID_SETTING}', true));
        """
    )
    op.execute(
        f"""
        CREATE POLICY jobs_update ON jobs FOR UPDATE
            USING (owner_id = current_setting('{USER_ID_SETTING}', true))
            WITH CHECK (owner_id = current_setting('{USER_ID_SETTING}', true));
        """
    )
    op.execute(
        f"""
        CREATE POLICY jobs_delete ON jobs FOR DELETE
            USING (owner_id = current_setting('{USER_ID_SETTING}', true));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS jobs_delete ON jobs;")
    op.execute("DROP POLICY IF EXISTS jobs_update ON jobs;")
    op.execute("DROP POLICY IF EXISTS jobs_insert ON jobs;")
    op.execute("DROP POLICY IF EXISTS jobs_select ON jobs;")
    op.execute("ALTER TABLE jobs DISABLE ROW LEVEL SECURITY;")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE jobs FROM {APP_ROLE};")

    op.drop_index("idx_jobs_owner_hash", table_name="jobs")
    op.drop_index("idx_jobs_owner_id", table_name="jobs")
    op.drop_constraint("fk_jobs_owner_id_user", "jobs", type_="foreignkey")
    op.drop_column("jobs", "attempts")
    op.drop_column("jobs", "processing_duration_seconds")
    op.drop_column("jobs", "cost_usd")
    op.drop_column("jobs", "token_usage")
    op.drop_column("jobs", "content_hash")
    op.drop_column("jobs", "owner_id")
