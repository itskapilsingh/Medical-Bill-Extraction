from app.core.context_manager import ContextManager
from app.dao.base_pg_dao import BasePgDAO
from app.dao.models.job import Job


class JobDAO(BasePgDAO[Job]):
    """Data access for the jobs table.

    All SQL lives here. No business logic — status transition rules
    belong in JobService, not here.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager, Job)

    def _to_orm(self, data: dict) -> Job:
        """Build a Job ORM instance from a plain dict."""
        raise NotImplementedError

    def _to_dto(self, orm: Job) -> dict:
        """Convert a Job ORM instance to a plain dict."""
        raise NotImplementedError

    def _apply_filters(self, query, filters: dict):
        """Apply optional status filter to a select query."""
        raise NotImplementedError

    async def create(self, pdf_filename: str, pdf_path: str) -> dict:
        """Insert a new job with status=pending. Returns the created job as a dict."""
        raise NotImplementedError

    async def get(self, job_id: str) -> dict | None:
        """Return a job by ID, or None if not found."""
        raise NotImplementedError

    async def list(self, status: str | None = None) -> list[dict]:
        """Return all jobs ordered by created_at desc. Optionally filter by status."""
        raise NotImplementedError

    async def get_active(self) -> list[dict]:
        """Return all jobs currently in processing status, or an empty list if all workers are idle."""
        raise NotImplementedError

    async def update_status(
        self,
        job_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> dict | None:
        """Update job status and optionally write result or error.

        Always update updated_at when calling this method.
        Returns the updated job as a dict, or None if job not found.
        """
        raise NotImplementedError

    async def cancel(self, job_id: str) -> bool:
        """Set a pending job to cancelled.

        Returns True if cancelled, False if job was not in pending status.
        Must be a no-op (return False, not raise) if job does not exist.
        """
        raise NotImplementedError

    async def claim_next_job(self) -> dict | None:
        """Atomically claim the next pending job for processing.

        Must guarantee that multiple concurrent workers never claim the same
        job. The implementation must be safe under concurrent access — think
        carefully about how to prevent two workers from picking up the same row.

        Returns the claimed job with status already set to 'processing',
        or None if the queue is empty.
        """
        raise NotImplementedError

    async def recover_stalled(self, timeout_minutes: int = 5) -> int:
        """Reset jobs stuck in processing back to pending.

        A job is stalled if its started_at is older than timeout_minutes
        and it is still in processing status. This recovers jobs from a
        worker that crashed before writing a completed or failed status.

        Returns the number of jobs recovered.
        """
        raise NotImplementedError
