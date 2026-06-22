"""Fixtures for database-backed tests.

These require a Postgres with the full migration chain applied (so the jobs
table has owner_id + RLS, and the billing_app role exists). The simplest way to
get that is the docker stack:

    docker compose up -d postgres api          # api runs the migrations
    POSTGRES_CONNECTION_STRING=postgresql+asyncpg://billing:billing@localhost:5432/billing \
    APP_DB_CONNECTION_STRING=postgresql+asyncpg://billing_app:billing_app@localhost:5432/billing \
    uv run pytest tests/integration

When no such database is reachable, every test here skips rather than fails.
"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ADMIN_URL = os.environ["POSTGRES_CONNECTION_STRING"]
APP_URL = os.environ["APP_DB_CONNECTION_STRING"]


def _probe(url: str) -> bool:
    """True if the URL is reachable AND the jobs.owner_id migration has run."""

    async def go() -> bool:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT owner_id FROM jobs WHERE false"))
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.run(go())
    except Exception:
        return False


_DB_READY = _probe(APP_URL) and _probe(ADMIN_URL)


@pytest.fixture(autouse=True)
def _require_db():
    if not _DB_READY:
        pytest.skip("Postgres with migrations not available")


@pytest_asyncio.fixture
async def admin_engine():
    engine = create_async_engine(ADMIN_URL)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def app_engine():
    engine = create_async_engine(APP_URL)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def two_users(admin_engine):
    """Create two users via the admin role; clean them up (and their jobs) after."""
    alice = f"test-user-{uuid.uuid4().hex}"
    bob = f"test-user-{uuid.uuid4().hex}"
    async with admin_engine.begin() as conn:
        for uid in (alice, bob):
            await conn.execute(
                text(
                    'INSERT INTO "user" (id, name, email) '
                    "VALUES (:id, :name, :email)"
                ),
                {"id": uid, "name": uid, "email": f"{uid}@example.com"},
            )
    try:
        yield alice, bob
    finally:
        async with admin_engine.begin() as conn:
            # ON DELETE CASCADE removes their jobs too.
            await conn.execute(
                text('DELETE FROM "user" WHERE id = ANY(:ids)'),
                {"ids": [alice, bob]},
            )
