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
  ai/        # OpenAI Agents SDK: extraction agent, tools, prompts, orchestrator
alembic/     # Schema migrations (run via the container entrypoint)
scripts/     # migrate.sh — runs alembic then exec's the process command
main.py      # API entry (uvicorn)
worker.py    # Background worker loop (drains gracefully on SIGTERM)
Dockerfile   # uv sync + .venv (Python 3.12); runs as a non-root user
```

PDF uploads land on the Docker-managed `pdf_data` named volume mounted at
`/app/pdfs`, shared by the API and worker; each PDF is deleted once its job
reaches a terminal state (see [`../SECURITY.md`](../SECURITY.md)).

## Run

Run the whole stack from the repo root with `docker compose up --build`; see the root
[`README.md`](../README.md). The compose `api` service runs `scripts/migrate.sh` (alembic
`upgrade head`) before starting Uvicorn, then the worker (2 replicas) starts once the API is
healthy. Inside the container everything lives under `/app`, so paths are unchanged from a
flat layout.

## Notes

- The API and worker must connect as the RLS-enforced application DB role
  (`APP_DB_CONNECTION_STRING`), not the migration or owner role. See `../ASSIGNMENT.md`.
- The `/jobs` routes and the extraction pipeline are fully implemented: the worker claims
  jobs with a `SECURITY DEFINER` function (`FOR UPDATE SKIP LOCKED`), runs the extraction
  agent under the job owner's identity, and persists results + metrics. M3 adds bounded
  retries with backoff, crash recovery for stalled jobs, and per-user content caching.
- Security/PHI hardening (security headers, rate limiting, upload + parse + LLM timeouts,
  PHI minimization, audit logging) is summarized in [`../SECURITY.md`](../SECURITY.md).
