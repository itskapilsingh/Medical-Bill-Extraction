import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.dao.models.base import Base
from app.dao.models.job import Job  # noqa: F401 — ensures Job is registered on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from environment, falling back to alembic.ini value."""
    return os.environ.get(
        "POSTGRES_CONNECTION_STRING",
        config.get_main_option("sqlalchemy.url"),
    )


def run_migrations_offline() -> None:
    """Run migrations in offline mode (generate SQL without a live connection)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Configure Alembic and run migrations inside a managed transaction.

    The ``with context.begin_transaction()`` wrapper is load-bearing: under
    SQLAlchemy 2.0 the connection autobegins a transaction on the first DDL
    statement, and without Alembic owning that transaction it is never committed
    — every migration would execute, log success, then roll back on close,
    leaving an empty database. begin_transaction() makes Alembic commit on
    success.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = create_async_engine(get_url())

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())


run()
