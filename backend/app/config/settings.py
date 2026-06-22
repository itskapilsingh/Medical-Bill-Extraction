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
    ENVIRONMENT: str = "development"
    WORKER_POLL_INTERVAL_SECONDS: int = 5

    # Echo every SQL statement (SQLAlchemy engine.echo). Off by default — it is
    # very noisy; turn on only when debugging queries. Kept separate from
    # ENVIRONMENT so dev logs stay readable.
    DB_ECHO: bool = False

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
