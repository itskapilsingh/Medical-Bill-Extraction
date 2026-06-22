# AGENTS.md

How to work in this repository — for an AI coding agent or a new engineer. Read this
before touching code. The design rationale lives in [`docs/design.md`](docs/design.md);
this file is the operational guide.

## What this is

A multi-user medical-billing extraction platform. A signed-in user uploads billing PDFs;
an async worker runs an extraction agent and persists structured records; the user sees
only their own jobs and results. Per-user isolation is enforced by **Postgres Row-Level
Security**, not by application `WHERE` clauses.

```
Next.js + Better Auth (web, :3000)  ──BFF proxy──>  FastAPI API (:8000)  ──>  Postgres (RLS)
        owns sessions                  Bearer token      billing_app role          jobs + auth tables
                                                          Worker (×2)  ──>  extraction agent (OpenAI)
```

## Repository layout

```
backend/            # Python API + worker (FastAPI, SQLAlchemy async, Alembic)
  app/
    api/            # routes, dependencies (auth, container), response schema
    config/         # pydantic-settings
    core/           # db provider, context manager (RLS identity), storage, identity
    dao/            # SQLAlchemy models + DAOs (all SQL lives here)
    service/        # business logic (job lifecycle, extraction)
    ai/             # OpenAI Agents SDK pipeline (echo demo today; extraction in M2)
    worker/         # background claim/process loop
  alembic/versions/ # migrations — the DB schema source of truth (incl. RLS + roles)
  tests/            # unit (no DB) + integration (DB-gated, skip without Postgres)
frontend/           # Next.js App Router + Better Auth + Tailwind
  app/api/auth/     # Better Auth handler
  app/api/backend/  # BFF proxy: validates session, forwards to API with Bearer token
  lib/auth.ts       # Better Auth server config (Postgres adapter)
docs/               # domain.md, schema.md, design.md (design.md is hand-written)
data/               # sample PDFs + ground truth (git-ignored)
docker-compose.yml  # postgres + api + worker (×2) + web
```

## Run the whole stack

```bash
cp .env.example .env          # then set OPENAI_API_KEY and a real BETTER_AUTH_SECRET
docker compose up --build
```

- Postgres comes up first; the `api` container runs `scripts/migrate.sh` (alembic
  `upgrade head`) before Uvicorn, so the schema — including the `billing_app` role, the
  Better Auth tables, and the RLS policies — exists before anything connects.
- `web` waits for the API healthcheck, then serves the UI on http://localhost:3000.
- Smoke test: open :3000, sign up, sign in, upload a PDF. Health: `curl localhost:8000/health`.

## Test

```bash
# Unit tests (no database needed):
cd backend && uv run pytest tests/unit

# Integration tests (RLS isolation + HTTP lifecycle) need a migrated Postgres.
# Easiest: bring up the stack, then point the tests at it.
docker compose up -d postgres api
cd backend && \
  POSTGRES_CONNECTION_STRING=postgresql+asyncpg://billing:billing@localhost:5432/billing \
  APP_DB_CONNECTION_STRING=postgresql+asyncpg://billing_app:billing_app@localhost:5432/billing \
  uv run pytest tests/integration
```

Integration tests skip (not fail) when no Postgres is reachable. `tests/integration/
test_rls_isolation.py` is the blunt isolation check; `test_jobs_api.py` is the end-to-end
lifecycle including unhappy paths.

The frontend builds with `cd frontend && npm install && npm run build`.

## Conventions

- **Layering is strict.** Routes → service (business rules) → DAO (all SQL) → DB. Routes
  never write SQL; DAOs never hold business rules. The AI layer is reached only via
  `ExtractionService`, never from routes.
- **Identity is out-of-band.** The authenticated user is held in a `contextvars` var
  (`app/core/identity.py`); `ContextManager.session()` stamps it onto each transaction with
  `set_config('app.user_id', …, local=true)`. Do **not** add `owner_id` filters in read
  queries — RLS is the enforcer, and reads are written without them on purpose so the
  isolation property is visible. Writes set `owner_id` from the authenticated user.
- **The DB schema lives in Alembic**, including roles and RLS policies. Never edit a shipped
  migration; add a new one. The `billing_app` role the app uses is non-owner and
  non-BYPASSRLS — keep it that way.
- **Better Auth tables are case-sensitive camelCase** (`"userId"`, `"expiresAt"`); always
  double-quote them in raw SQL. `session.token` stores the raw token; the API validates by
  direct lookup.
- **Commits** are small, coherent, conventional-commit style (`feat(api): …`), with honest
  messages. The git history is part of the submission — do not squash.
- **Line endings**: `.gitattributes` forces LF so shell scripts survive Windows → Linux
  containers.

## Gotchas

- The browser never calls the API directly (SameSite=Lax would drop the cookie cross-origin
  to :8000). It calls the same-origin BFF proxy at `/api/backend/*`, which forwards to the
  API with the session token as a Bearer credential.
- The worker has no HTTP session: in M2 it claims a job, reads `owner_id`, and runs under
  `acting_as(owner_id)` so its writes are RLS-scoped to that owner.
- `gpt-5.4` family only for extraction (no `-pro` variants). Keep LLM calls modest.
