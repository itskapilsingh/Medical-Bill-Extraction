from __future__ import annotations

from time import perf_counter

from app.ai.context import RunContext
from app.ai.orchestrator import ExtractionOrchestrator
from app.ai.pdf_loader import load_document
from app.core.context_manager import ContextManager
from app.dao.pg.job_dao import JobDAO
from app.service.base_service import BaseService


class ExtractionService(BaseService):
    """Owns the extraction pipeline for a single claimed job.

    Called by the worker loop AFTER the job has been claimed and the worker has
    bound the job owner's identity (``acting_as(owner_id)``), so every DB write
    here is RLS-scoped to that owner. Responsible for loading the PDF, running the
    orchestrator, and writing the result or error back.

    Never raises: any failure is caught and written to the job's error field so
    the worker loop stays alive and the job ends in a terminal ``failed`` state.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager)
        self.job_dao = JobDAO(context_manager)

    async def process_job(self, job_id: str) -> None:
        """Run the full extraction pipeline for an already-claimed job."""
        start = perf_counter()
        try:
            job = await self.job_dao.get(job_id)
            if job is None:
                # RLS-invisible or already gone — nothing safe to do.
                self.logger.warning("process_job_not_visible", job_id=job_id)
                return

            document = load_document(job["pdf_path"], job_id)
            result = await ExtractionOrchestrator().run(RunContext(document=document))
            duration = round(perf_counter() - start, 3)

            await self.job_dao.update_status(
                job_id,
                "completed",
                result={
                    "records": [r.model_dump() for r in result.extraction.records],
                    "flagged": [f.model_dump() for f in result.extraction.flagged],
                },
                token_usage=result.token_usage,
                cost_usd=result.cost_usd,
                processing_duration_seconds=duration,
            )
            self.logger.info(
                "job_completed",
                job_id=job_id,
                records=len(result.extraction.records),
                flagged=len(result.extraction.flagged),
                cost_usd=result.cost_usd,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = round(perf_counter() - start, 3)
            self.logger.exception("job_failed", job_id=job_id)
            try:
                await self.job_dao.update_status(
                    job_id,
                    "failed",
                    error=f"{type(exc).__name__}: {exc}",
                    processing_duration_seconds=duration,
                )
            except Exception:
                # Last-ditch: never let a status-write failure escape the worker.
                self.logger.exception("job_failed_status_write_error", job_id=job_id)
