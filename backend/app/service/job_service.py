from app.core.context_manager import ContextManager
from app.dao.pg.job_dao import JobDAO
from app.service.base_service import BaseService


class JobService(BaseService):
    """Owns the job lifecycle: creation, status queries, and cancellation.

    All database access goes through JobDAO. This service does not interact
    with the AI layer — that is ExtractionService's responsibility.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager)
        self.job_dao = JobDAO(context_manager)

    async def create_job(self, pdf_filename: str, pdf_path: str) -> dict:
        """Create a new job in pending status. Returns the created job as a dict."""
        raise NotImplementedError

    async def get_job(self, job_id: str) -> dict:
        """Return a job by ID. Raises JobNotFoundException if not found."""
        raise NotImplementedError

    async def list_jobs(self, status: str | None = None) -> list[dict]:
        """Return all jobs ordered by created_at desc. Optionally filter by status."""
        raise NotImplementedError

    async def get_active_jobs(self) -> list[dict]:
        """Return all currently processing jobs, or an empty list if all workers are idle."""
        raise NotImplementedError

    async def cancel_job(self, job_id: str) -> dict:
        """Cancel a pending job.

        Raises JobNotFoundException if job does not exist.
        Raises JobNotCancellableException if job is not in pending status.
        Returns the updated job as a dict.
        """
        raise NotImplementedError
