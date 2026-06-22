from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.database.postgres import PostgresProvider
from app.core.identity import get_current_user_id


class ContextManager:
    """Owns the database connection lifecycle for the application.

    Created once at startup and stored on app.state.
    Pass into services and DAOs via dependency injection.
    Call initialize() before use and close() on shutdown.

    Every session opened here connects as the RLS-enforced application role and,
    if an authenticated identity is bound to the current context, stamps it onto
    the transaction so Row-Level Security policies can act on it.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._postgres: PostgresProvider | None = None

    async def initialize(self) -> None:
        """Create the database engine and session factory. Call once at startup."""
        self._postgres = PostgresProvider(
            # The application connects as the RLS-enforced role — NOT the schema
            # owner and NOT a BYPASSRLS role. This is the load-bearing line of the
            # isolation guarantee: even a wrong WHERE clause cannot cross users
            # because the database filters every row by current_setting('app.user_id').
            connection_string=self._settings.APP_DB_CONNECTION_STRING,
            connection_settings={
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "pool_pre_ping": True,
                "echo": self._settings.DB_ECHO,
            },
        )

    async def close(self) -> None:
        """Dispose the database engine. Call on shutdown."""
        if self._postgres:
            await self._postgres.close()
            self._postgres = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a database session bound to the current user's RLS identity.

        Commits on clean exit, rolls back on exception. If an authenticated user
        is bound to the current context, the very first statement in the
        transaction sets ``app.user_id`` LOCAL to this transaction; it is reset
        automatically on COMMIT/ROLLBACK, so a reused pooled connection never
        carries a stale identity.
        """
        if self._postgres is None:
            raise RuntimeError("ContextManager not initialized. Call initialize() first.")
        async with await self._postgres.get_session() as session:
            try:
                await self._apply_identity(session)
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _apply_identity(self, session: AsyncSession) -> None:
        """Stamp the bound user id onto the transaction via set_config(..., local=true).

        Runs as the first statement, which also begins the transaction, so every
        subsequent query sees the GUC. When no identity is bound the GUC is left
        unset and RLS denies all user-owned rows (default-deny).
        """
        user_id = get_current_user_id()
        if user_id is None:
            return
        await session.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": self._settings.RLS_USER_ID_SETTING, "value": str(user_id)},
        )

    async def health_check(self) -> bool:
        """Check live database connectivity. Used by GET /health."""
        if self._postgres is None:
            return False
        return await self._postgres.health_check()
