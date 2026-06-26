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
import re
from typing import Sequence, Union

from alembic import op

revision: str = "a1771a9c2e01"
down_revision: Union[str, Sequence[str], None] = "0de1443cd0f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "billing_app"
APP_PASSWORD = os.environ.get("APP_DB_PASSWORD", "billing_app")
DB_NAME = os.environ.get("POSTGRES_DB", "billing")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(value: str) -> str:
    if not _IDENT.fullmatch(value):
        raise ValueError(f"Unsafe PostgreSQL identifier: {value!r}")
    return value


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    role = _ident(APP_ROLE)
    db_name = _ident(DB_NAME)
    password = _literal(APP_PASSWORD)
    role_literal = _literal(role)

    # Create the login role if it does not already exist (roles survive across
    # database drops within a cluster, so CREATE ROLE must be guarded).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {role_literal}) THEN
                CREATE ROLE {role} LOGIN PASSWORD {password};
            END IF;
        END
        $$;
        """
    )

    op.execute(f"GRANT CONNECT ON DATABASE {db_name} TO {role};")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role};")


def downgrade() -> None:
    role = _ident(APP_ROLE)
    db_name = _ident(DB_NAME)
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role};")
    op.execute(f"REVOKE CONNECT ON DATABASE {db_name} FROM {role};")
