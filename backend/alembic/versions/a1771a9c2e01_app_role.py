"""create the RLS-enforced application role

Roles are cluster-global, so this runs idempotently. The application (API +
worker) connects as ``billing_app``: it is NOT the schema owner and has NO
BYPASSRLS / superuser attribute, so every statement it runs is subject to the
Row-Level Security policies added in later migrations. Migrations themselves run
as the admin/owner role (POSTGRES_CONNECTION_STRING) and are unaffected.

The role's password is taken from APP_DB_PASSWORD (falling back to the dev value
that matches .env.example), and the database name from POSTGRES_DB. Set
APP_DB_PASSWORD from your secrets manager in a real deployment and make
APP_DB_CONNECTION_STRING use the same value; the defaults are dev-only.

Revision ID: a1771a9c2e01
Revises: 0de1443cd0f2
Create Date: 2026-06-22

"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "a1771a9c2e01"
down_revision: Union[str, Sequence[str], None] = "0de1443cd0f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "billing_app"
# Operator-controlled (migration-time), not user input. Default preserves the
# existing local credential so a no-config boot behaves exactly as before.
APP_PASSWORD = os.environ.get("APP_DB_PASSWORD", "billing_app")
DB_NAME = os.environ.get("POSTGRES_DB", "billing")


def upgrade() -> None:
    # Create the login role if it does not already exist (roles survive across
    # database drops within a cluster, so CREATE ROLE must be guarded).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}';
            END IF;
        END
        $$;
        """
    )

    # Baseline connect/usage only. Object-level privileges are granted explicitly
    # per table in the migration that creates (or owns) that table, so the role
    # gets exactly what it needs and no more — full DML on jobs, read-only on the
    # auth tables it validates against. We deliberately avoid a blanket
    # ALTER DEFAULT PRIVILEGES, which would silently hand the app role write
    # access to the Better Auth tables too.
    op.execute(f"GRANT CONNECT ON DATABASE {DB_NAME} TO {APP_ROLE};")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE};")


def downgrade() -> None:
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};")
    op.execute(f"REVOKE CONNECT ON DATABASE {DB_NAME} FROM {APP_ROLE};")
    # The role itself is intentionally left in place on downgrade; dropping a role
    # that may own privileges elsewhere is unsafe to do blindly.
