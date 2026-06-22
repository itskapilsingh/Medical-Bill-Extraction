"""Better Auth tables (user / session / account / verification)

These tables are authored here, in Alembic, so the whole schema is owned and
migrated in one place (the admin role) rather than split between Alembic and
Better Auth's own CLI. The DDL matches better-auth's expected schema exactly:
camelCase, double-quoted, case-sensitive identifiers; ``id`` is application-
generated ``text`` with no DB default; ``session.token`` stores the RAW token
(not a hash) and is UNIQUE, which is what lets the API validate a presented
token with a single equality lookup.

Isolation note: these are authentication/infrastructure tables, not user-owned
business data, so they are intentionally left WITHOUT per-user RLS — the API
must be able to look a session up *before* it knows who the user is. The app
role is granted SELECT (read-only) on "user" and "session" so it can validate
sessions, and nothing on "account"/"verification" (password hashes, tokens). It
can never write any auth table. Better Auth, running in Next.js, owns writes via
the admin role (DATABASE_URL).

Revision ID: b2c4e6a80f11
Revises: a1771a9c2e01
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c4e6a80f11"
down_revision: Union[str, Sequence[str], None] = "a1771a9c2e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "billing_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE "user" (
            "id"            text PRIMARY KEY NOT NULL,
            "name"          text NOT NULL,
            "email"         text NOT NULL UNIQUE,
            "emailVerified" boolean NOT NULL DEFAULT false,
            "image"         text,
            "createdAt"     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt"     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute(
        """
        CREATE TABLE "session" (
            "id"        text PRIMARY KEY NOT NULL,
            "expiresAt" timestamptz NOT NULL,
            "token"     text NOT NULL UNIQUE,
            "createdAt" timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt" timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "ipAddress" text,
            "userAgent" text,
            "userId"    text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE
        );
        """
    )
    op.execute('CREATE INDEX "session_userId_idx" ON "session" ("userId");')
    op.execute(
        """
        CREATE TABLE "account" (
            "id"                    text PRIMARY KEY NOT NULL,
            "accountId"             text NOT NULL,
            "providerId"            text NOT NULL,
            "userId"                text NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
            "accessToken"           text,
            "refreshToken"          text,
            "idToken"               text,
            "accessTokenExpiresAt"  timestamptz,
            "refreshTokenExpiresAt" timestamptz,
            "scope"                 text,
            "password"              text,
            "createdAt"             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt"             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute('CREATE INDEX "account_userId_idx" ON "account" ("userId");')
    op.execute(
        """
        CREATE TABLE "verification" (
            "id"         text PRIMARY KEY NOT NULL,
            "identifier" text NOT NULL,
            "value"      text NOT NULL,
            "expiresAt"  timestamptz NOT NULL,
            "createdAt"  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updatedAt"  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute(
        'CREATE INDEX "verification_identifier_idx" ON "verification" ("identifier");'
    )

    # The app role may READ user + session (to authenticate requests) and nothing
    # more. No write privileges on any auth table; no access to account/verification.
    op.execute(f'GRANT SELECT ON TABLE "user" TO {APP_ROLE};')
    op.execute(f'GRANT SELECT ON TABLE "session" TO {APP_ROLE};')


def downgrade() -> None:
    op.execute(f'REVOKE SELECT ON TABLE "session" FROM {APP_ROLE};')
    op.execute(f'REVOKE SELECT ON TABLE "user" FROM {APP_ROLE};')
    op.execute('DROP TABLE IF EXISTS "verification";')
    op.execute('DROP TABLE IF EXISTS "account";')
    op.execute('DROP TABLE IF EXISTS "session";')
    op.execute('DROP TABLE IF EXISTS "user";')
