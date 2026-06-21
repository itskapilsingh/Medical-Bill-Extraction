# Medical Billing Records Platform

Starter stack for the medical billing extraction take-home: a full-stack, multi-user
platform where an authenticated user uploads PDFs and an async pipeline extracts structured
billing records scoped strictly to that user. The full specification lives in
**[ASSIGNMENT.md](ASSIGNMENT.md)**; read it first.

You are extending this starter into a system with three parts:

- a Next.js web frontend with Better Auth for sign up, sign in, and sessions (you add this)
- a Python/FastAPI API and async worker (provided, stubbed) that does the extraction
- Postgres with Row-Level Security for per-user isolation (you design the policies)

> Per-user isolation must be enforced by RLS in the database, not by application-layer
> `WHERE` clauses alone. See *The Backend Lever* in [ASSIGNMENT.md](ASSIGNMENT.md).

## Repository layout

```
backend/         # Python API + worker (provided, stubbed) — see backend/README.md
  app/
    api/         # FastAPI app, routes, dependencies
    config/      # Settings (pydantic-settings / .env)
    core/        # DB provider, logging, context manager
    dao/         # SQLAlchemy models and DAOs
    models/      # Pydantic output types — extraction.py is the canonical shape
    service/     # Business logic
    ai/          # OpenAI Agents SDK tools, prompts, echo demo, orchestrator
  alembic/       # Schema migrations (run via the API container entrypoint)
  scripts/       # migrate.sh — runs alembic then exec's the process command
  pdfs/          # shared upload volume (mounted into api + worker)
  Dockerfile     # uv sync + .venv (Python 3.12)
  main.py        # API entry (uvicorn)
  worker.py      # Background worker loop
frontend/        # YOU BUILD THIS — Next.js + Better Auth (placeholder README inside)
docs/            # domain.md, schema.md, design.md (assignment references)
data/            # sample PDFs + ground truth (when shipped; git-ignored)
docker-compose.yml   # whole stack: postgres + api + worker (+ your web service)
.env.example
```

The whole stack still comes up from the repo root with one `docker compose up`. Inside the
containers the backend lives at `/app`, so paths are unchanged from a flat layout; the split
is host-side only.

## What is provided vs. what you build

Provided (stubbed where noted): the Python API, worker, and Postgres, plus Alembic
migrations, the Docker build, the AI `echo` demo, and `NotImplementedError` stubs for job
lifecycle, extraction persistence, and worker claiming.

You build: the Next.js frontend, the Better Auth integration, the RLS policies and the
RLS-enforced application DB role, the identity plumbing that runs from auth through the API
and database session down to the worker, and the extraction pipeline itself. Wire the
frontend into `docker-compose.yml` so the whole stack still comes up with one command.

## Prerequisites

- Docker with Compose v2.
- A `.env` is already provided, with a working `OPENAI_API_KEY` and the Postgres defaults.
  Set `BETTER_AUTH_SECRET` to a real random value before running. `.env.example` documents
  every variable, including the two database identities: an admin role for migrations and an
  RLS-enforced application role for the API and worker.

## Run with Docker Compose

From the repo root:

```bash
docker compose up --build
```

- Postgres starts first, and is healthy before its dependents.
- The API runs `scripts/migrate.sh` then `python main.py`, so migrations apply before
  Uvicorn.
- The worker waits until the API healthcheck passes (2 replicas by default).
- The web service (Next.js), once you add it, serves the UI and Better Auth on port `3000`.

PDF uploads use the `pdfs/` volume mounted at `/app/pdfs` inside the API and worker.

## Smoke-test the stack

1. Health (DB connectivity), a public endpoint:

   ```bash
   curl -s http://localhost:8000/health | python -m json.tool
   ```

   Expected: `{"status": "ok", "db": "ok"}`.

2. Frontend and auth: open [http://localhost:3000](http://localhost:3000), sign up, sign in,
   and upload a PDF. A job should appear, and once the worker finishes you should see its
   extracted result, visible only to your account.

3. Isolation check, the bar that matters: signed in as user A, try to fetch user B's job by
   ID, both via the API and directly against the DB as the app role. You must get nothing.
   See *The Isolation Guarantee* in [ASSIGNMENT.md](ASSIGNMENT.md).

4. Backend API docs: [http://localhost:8000/docs](http://localhost:8000/docs) for Swagger
   UI. The `/jobs` routes require authentication and return only the caller's data.

5. Worker:

   ```bash
   docker compose logs worker --tail 30
   ```

   You should see structured `worker_started` logs and the polling loop, with no crash loop.

Note: the `/jobs` routes ship as stubs (`NotImplementedError`) until you implement
`JobService` and `JobDAO`. The working AI demo today is the `echo` path (`EchoAgentExecutor`
plus `ExtractionOrchestrator`), wired for local experimentation and not yet hooked to HTTP
job processing.

## Tear down

```bash
docker compose down -v
```

`-v` removes the Postgres volume, giving you a fresh DB next time.

---

For milestones, evaluation criteria, the API contract, the RLS requirements, and
deliverables, read **[ASSIGNMENT.md](ASSIGNMENT.md)**. Fill in
**[docs/design.md](docs/design.md)** by hand and add a root **`AGENTS.md`**.
