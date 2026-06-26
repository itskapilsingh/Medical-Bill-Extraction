from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str

    POSTGRES_CONNECTION_STRING: str

    APP_DB_CONNECTION_STRING: str

    RLS_USER_ID_SETTING: str = "app.user_id"

    BETTER_AUTH_SECRET: str

    # App
    PDF_MOUNT_PATH: str = "/app/pdfs"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production"
    API_RELOAD: bool = False
    WORKER_POLL_INTERVAL_SECONDS: int = 5
    WORKER_CONCURRENCY: int = 4

    # Hard cap on uploaded PDF size (bytes). Rejected with 413 above this.
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB
    MAX_UPLOAD_REQUEST_BYTES: int = MAX_UPLOAD_BYTES + (1024 * 1024)

    # Resource bounds for hostile/large PDFs and slow model calls.
    PDF_MAX_PAGES: int = 400
    PDF_PARSE_TIMEOUT_SECONDS: float = 60.0
    EXTRACTION_TIMEOUT_SECONDS: float = 180.0

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 120          # per-IP general API budget / window
    RATE_LIMIT_UPLOAD_MAX_REQUESTS: int = 15    # per-IP budget for POST /jobs / window
    RATE_LIMIT_USER_UPLOAD_MAX_REQUESTS: int = 10  # per-USER budget for POST /jobs / window
    TRUSTED_PROXIES: str = ""

    DELETE_PDF_AFTER_PROCESSING: bool = True
    RETENTION_DAYS: int = 30
    RETENTION_SWEEP_INTERVAL_SECONDS: int = 3600

    DB_ECHO: bool = False

    EXTRACTION_MAX_ATTEMPTS: int = 3
    EXTRACTION_BACKOFF_BASE_SECONDS: float = 2.0
    EXTRACTION_MAX_TURNS: int = 40

    EXTRACTION_MODEL: str
    PDF_FILE_EXTRACTION_MODEL: str

    LLM_PRICING_EFFECTIVE_DATE: str = "2026-06-24"
    LLM_PRICE_GPT_5_4_INPUT_PER_1M: float = 1.25
    LLM_PRICE_GPT_5_4_CACHED_INPUT_PER_1M: float = 0.125
    LLM_PRICE_GPT_5_4_OUTPUT_PER_1M: float = 10.0
    LLM_PRICE_GPT_5_4_MINI_INPUT_PER_1M: float = 0.25
    LLM_PRICE_GPT_5_4_MINI_CACHED_INPUT_PER_1M: float = 0.025
    LLM_PRICE_GPT_5_4_MINI_OUTPUT_PER_1M: float = 2.0
    LLM_PRICE_GPT_5_4_NANO_INPUT_PER_1M: float = 0.05
    LLM_PRICE_GPT_5_4_NANO_CACHED_INPUT_PER_1M: float = 0.005
    LLM_PRICE_GPT_5_4_NANO_OUTPUT_PER_1M: float = 0.40

    WORKER_STALL_TIMEOUT_MINUTES: int = 15

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }

    @property
    def trusted_proxy_set(self) -> frozenset[str]:
        """TRUSTED_PROXIES parsed into a set of IP strings (empty by default)."""
        return frozenset(p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip())

    @property
    def worst_case_job_seconds(self) -> float:
        """Upper bound on one claim's wall clock: PDF parse + every retry
        attempt's extraction timeout + the exponential backoffs between attempts."""
        backoffs = sum(
            self.EXTRACTION_BACKOFF_BASE_SECONDS * (2 ** (i - 1))
            for i in range(1, self.EXTRACTION_MAX_ATTEMPTS)
        )
        return (
            self.PDF_PARSE_TIMEOUT_SECONDS
            + self.EXTRACTION_MAX_ATTEMPTS * self.EXTRACTION_TIMEOUT_SECONDS
            + backoffs
        )

    @model_validator(mode="after")
    def _validate_invariants(self) -> "Settings":
        stall_seconds = self.WORKER_STALL_TIMEOUT_MINUTES * 60
        if stall_seconds < self.worst_case_job_seconds:
            raise ValueError(
                f"WORKER_STALL_TIMEOUT_MINUTES ({self.WORKER_STALL_TIMEOUT_MINUTES} min "
                f"= {stall_seconds}s) must exceed the worst-case job runtime of "
                f"{self.worst_case_job_seconds:.0f}s (PDF parse + "
                f"{self.EXTRACTION_MAX_ATTEMPTS} x {self.EXTRACTION_TIMEOUT_SECONDS}s "
                f"extraction + backoffs). A shorter window makes recovery re-queue "
                f"running jobs and double-charge the model."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
