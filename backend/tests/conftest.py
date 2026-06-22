"""Shared test configuration.

Unit tests (tests/unit) run anywhere — pure logic, no database. Integration
tests (tests/integration) need a live Postgres with the migrations applied and
the billing_app role created; they skip cleanly when one is not configured.
"""

import os

# Provide defaults so importing modules that read settings never explodes during
# collection. Real values come from the environment in integration runs.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault(
    "POSTGRES_CONNECTION_STRING",
    "postgresql+asyncpg://billing:billing@localhost:5432/billing",
)
os.environ.setdefault(
    "APP_DB_CONNECTION_STRING",
    "postgresql+asyncpg://billing_app:billing_app@localhost:5432/billing",
)
os.environ.setdefault("BETTER_AUTH_SECRET", "test-secret-do-not-use-in-prod")
