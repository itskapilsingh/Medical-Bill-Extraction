from app.core.context_manager import ContextManager
from app.dao.pg.job_dao import JobDAO
from app.service.base_service import BaseService


class ExtractionService(BaseService):
    """Owns the extraction pipeline for a single job.

    Called by the worker loop with a job_id. Responsible for:
    - Loading the PDF from the mounted volume
    - Building RunContext and running ExtractionOrchestrator
    - Writing the extraction result or error back to the job record

    This service is the bridge between the job queue and the AI layer.
    Never raises — all exceptions must be caught and written to the job
    error field so the worker loop stays alive.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager)
        self.job_dao = JobDAO(context_manager)

    async def process_job(self, job_id: str) -> None:
        """Run the full extraction pipeline for a job.

        Loads the PDF, builds RunContext, runs the orchestrator, writes
        result back. Updates job status to completed or failed.
        Must never raise — catch all exceptions and write to job.error.
        """
        raise NotImplementedError
