from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str

    # Postgres — admin / migration role. Owns the schema; used ONLY by Alembic
    # (see alembic/env.py). The application never connects with this.
    POSTGRES_CONNECTION_STRING: str

    # Postgres — application role. RLS-ENFORCED, non-owner, no BYPASSRLS.
    # Every API request and every worker job connects through this role, so a
    # missing/forgotten WHERE clause cannot leak another user's rows: the
    # database itself filters by current_setting('app.user_id').
    APP_DB_CONNECTION_STRING: str

    # Name of the Postgres session GUC that carries the authenticated user id
    # into the database session. RLS policies read it via current_setting().
    RLS_USER_ID_SETTING: str = "app.user_id"

    # Auth (Better Auth, issued by the Next.js app). The API uses the shared
    # session table to validate the presented token, and the secret to verify
    # the signed cookie value before trusting it.
    BETTER_AUTH_SECRET: str = "change_me_to_a_long_random_string"

    # App
    PDF_MOUNT_PATH: str = "/app/pdfs"
    LOG_LEVEL: str = "INFO"
    # Default to production so an unconfigured deployment is safe-by-default
    # (JSON logs, no SQL echo, no auto-reload). Set ENVIRONMENT=development locally.
    ENVIRONMENT: str = "production"
    # Uvicorn auto-reload is decoupled from ENVIRONMENT and OFF by default — it
    # must never run in a real deployment. Opt in locally with API_RELOAD=true.
    API_RELOAD: bool = False
    WORKER_POLL_INTERVAL_SECONDS: int = 5

    # Hard cap on uploaded PDF size (bytes). Rejected with 413 above this.
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB

    # Resource bounds for hostile/large PDFs and slow model calls.
    PDF_MAX_PAGES: int = 400
    PDF_PARSE_TIMEOUT_SECONDS: float = 60.0
    EXTRACTION_TIMEOUT_SECONDS: float = 180.0

    # Per-IP request rate limiting (in-process; use a shared store for >1 replica).
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 120          # general API budget per window
    RATE_LIMIT_UPLOAD_MAX_REQUESTS: int = 15    # stricter budget for POST /jobs

    # PHI retention: delete the source PDF once a job reaches a terminal state,
    # and sweep PDFs left on the volume older than this many days (0 disables the
    # sweep). RETENTION_SWEEP_INTERVAL_SECONDS is how often the worker runs it.
    DELETE_PDF_AFTER_PROCESSING: bool = True
    RETENTION_DAYS: int = 30
    RETENTION_SWEEP_INTERVAL_SECONDS: int = 3600

    # Echo every SQL statement (SQLAlchemy engine.echo). Off by default — it is
    # very noisy; turn on only when debugging queries. Kept separate from
    # ENVIRONMENT so dev logs stay readable.
    DB_ECHO: bool = False

    # Reliability (M3).
    # Bounded retries for transient extraction failures (rate limit, timeout,
    # 5xx, connection). Total attempts including the first; backoff is
    # exponential: base * 2**(attempt-1) seconds.
    EXTRACTION_MAX_ATTEMPTS: int = 3
    EXTRACTION_BACKOFF_BASE_SECONDS: float = 2.0
    # Max tool-calling turns the extraction agent may take before being forced to
    # finish. Generous so large multi-provider documents don't exhaust it.
    EXTRACTION_MAX_TURNS: int = 40
    # A job in 'processing' longer than this is presumed orphaned by a crashed
    # worker and recovered (well above the few seconds a real job takes).
    WORKER_STALL_TIMEOUT_MINUTES: int = 5

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
