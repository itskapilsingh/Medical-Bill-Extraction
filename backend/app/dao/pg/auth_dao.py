"""Read-only access to the Better Auth tables for session validation.

This is the seam where the "shared session table" topology lives: the Next.js
app (Better Auth) writes ``session`` rows; this DAO reads them to resolve the
authenticated user for an incoming API request. It runs *before* any identity is
bound to the context, so the lookup is unscoped — which is correct, because the
auth tables carry no per-user RLS (you cannot scope a query by a user you have
not yet identified).

Identifiers are double-quoted because Better Auth stores them case-sensitively in
camelCase (``"userId"``, ``"expiresAt"``); unquoted, Postgres would fold them to
lowercase and the lookup would silently miss.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.context_manager import ContextManager

# Only non-expired sessions resolve. Expiry is evaluated in the database so we
# never depend on app/DB clock skew beyond Postgres' own now().
_SESSION_LOOKUP = text(
    """
    SELECT s."userId" AS user_id,
           u."email"  AS email,
           u."name"   AS name
    FROM "session" s
    JOIN "user" u ON u."id" = s."userId"
    WHERE s."token" = :token
      AND s."expiresAt" > now()
    """
)


class AuthDAO:
    def __init__(self, context_manager: ContextManager) -> None:
        self.context_manager = context_manager

    async def get_session_user(self, raw_token: str) -> dict[str, Any] | None:
        """Resolve a raw session token to its user, or None if invalid/expired."""
        if not raw_token:
            return None
        async with self.context_manager.session() as session:
            row = (await session.execute(_SESSION_LOOKUP, {"token": raw_token})).first()
        if row is None:
            return None
        return {"id": row.user_id, "email": row.email, "name": row.name}
