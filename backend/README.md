# Backend — API + Worker

The Python (FastAPI) extraction backend: an async API and worker over Postgres. This is one
half of the full-stack platform. The web frontend lives in [`../frontend`](../frontend), and
the whole stack is orchestrated from the repo-root `docker-compose.yml`. The full
specification is in [`../ASSIGNMENT.md`](../ASSIGNMENT.md).

## Layout

```
app/
  api/       # FastAPI app, routes, dependencies
  config/    # Settings (pydantic-settings / .env)
  core/      # DB provider, logging, context manager
  dao/       # SQLAlchemy models and DAOs
  models/    # Pydantic output types — extraction.py is the canonical shape
  service/   # Business logic
  ai/        # OpenAI Agents SDK tools, prompts, echo demo, orchestrator
alembic/     # Schema migrations (run via the container entrypoint)
scripts/     # migrate.sh — runs alembic then exec's the process command
pdfs/        # shared upload volume (mounted into api + worker)
main.py      # API entry (uvicorn)
worker.py    # Background worker loop
Dockerfile   # uv sync + .venv (Python 3.12)
```

## Run

Run the whole stack from the repo root with `docker compose up --build`; see the root
[`README.md`](../README.md). The compose `api` service runs `scripts/migrate.sh` (alembic
`upgrade head`) before starting Uvicorn, then the worker (2 replicas) starts once the API is
healthy. Inside the container everything lives under `/app`, so paths are unchanged from a
flat layout.

## Notes

- The API and worker must connect as the RLS-enforced application DB role
  (`APP_DB_CONNECTION_STRING`), not the migration or owner role. See `../ASSIGNMENT.md`.
- The `/jobs` routes and the extraction pipeline ship as `NotImplementedError` stubs; that
  is your work. The `echo` agent under `app/ai/` is a wiring example, not the solution.
