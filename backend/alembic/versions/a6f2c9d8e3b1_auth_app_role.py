"""create Better Auth application role

The Next.js web process should not connect as the schema owner. Better Auth
needs write access only to its own authentication tables, while the Python API
and worker keep using the RLS-enforced ``billing_app`` role for business data.

Revision ID: a6f2c9d8e3b1
Revises: f6b9c2d3e4a7
Create Date: 2026-06-24

"""
from __future__ import annotations

import os
import re
from typing import Sequence, Union

from alembic import op

revision: str = "a6f2c9d8e3b1"
down_revision: Union[str, Sequence[str], None] = "f6b9c2d3e4a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_ROLE = os.environ.get("AUTH_DB_ROLE", "billing_auth")
AUTH_PASSWORD = os.environ.get("AUTH_DB_PASSWORD", "billing_auth")
DB_NAME = os.environ.get("POSTGRES_DB", "billing")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(value: str) -> str:
    if not _IDENT.fullmatch(value):
        raise ValueError(f"Unsafe PostgreSQL identifier: {value!r}")
    return value


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    role = _ident(AUTH_ROLE)
    db_name = _ident(DB_NAME)
    password = _literal(AUTH_PASSWORD)
    role_literal = _literal(role)

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {role_literal}) THEN
                CREATE ROLE {role}
                    LOGIN
                    PASSWORD {password}
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOINHERIT
                    NOBYPASSRLS;
            ELSE
                ALTER ROLE {role} PASSWORD {password};
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT CONNECT ON DATABASE {db_name} TO {role};")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role};")
    for table in ('"user"', '"session"', '"account"', '"verification"'):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {role};")


def downgrade() -> None:
    role = _ident(AUTH_ROLE)
    db_name = _ident(DB_NAME)
    for table in ('"verification"', '"account"', '"session"', '"user"'):
        op.execute(
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {table} FROM {role};"
        )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role};")
    op.execute(f"REVOKE CONNECT ON DATABASE {db_name} FROM {role};")
    # Keep the role itself; cluster-global role deletion is unsafe on downgrade.
