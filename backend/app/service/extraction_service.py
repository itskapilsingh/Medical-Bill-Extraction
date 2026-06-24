from __future__ import annotations

import asyncio
from time import perf_counter

from app.ai.config import EXTRACTION_AGENT_CONFIG
from app.ai.context import RunContext
from app.ai.metrics import usage_from_exception, usage_to_token_dict
from app.ai.orchestrator import ExtractionOrchestrator, OrchestratorResult
from app.ai.pdf_loader import load_document
from app.ai.pricing import estimate_cost_usd
from app.ai.retry import is_transient
from app.config.settings import get_settings
from app.core.context_manager import ContextManager
from app.dao.pg.job_dao import JobDAO
from app.service.base_service import BaseService


class ExtractionService(BaseService):
    """Owns the extraction pipeline for a single claimed job.

    Called by the worker loop AFTER the job has been claimed and the worker has
    bound the job owner's identity (``acting_as(owner_id)``), so every DB write
    here is RLS-scoped to that owner. Responsible for loading the PDF, running the
    orchestrator (with bounded retries on transient failures), and writing the
    result or error back.

    Never raises: any failure is caught and written to the job's error field so
    the worker loop stays alive and the job ends in a terminal ``failed`` state.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager)
        self.job_dao = JobDAO(context_manager)
        settings = get_settings()
        self.max_attempts = max(1, settings.EXTRACTION_MAX_ATTEMPTS)
        self.backoff_base = settings.EXTRACTION_BACKOFF_BASE_SECONDS
        self.pdf_parse_timeout = settings.PDF_PARSE_TIMEOUT_SECONDS
        self.extraction_timeout = settings.EXTRACTION_TIMEOUT_SECONDS
        self.pdf_max_pages = settings.PDF_MAX_PAGES
        self.delete_pdf_after = settings.DELETE_PDF_AFTER_PROCESSING

    async def process_job(self, job_id: str, expected_attempts: int | None = None) -> None:
        """Run the full extraction pipeline for an already-claimed job.

        ``expected_attempts`` is the attempts value the worker claimed; it guards
        the terminal write so a run that was recovered out from under us (crash
        recovery re-queued the job and another worker re-claimed it) cannot
        overwrite the newer run's result.
        """
        start = perf_counter()
        try:
            job = await self.job_dao.get(job_id)
            if job is None:
                # RLS-invisible or already gone — nothing safe to do.
                self.logger.warning("process_job_not_visible", job_id=job_id)
                return

            # Parse off the event loop (pdfplumber is sync) and bound it: a hostile
            # or huge PDF cannot pin the worker indefinitely.
            document = await asyncio.wait_for(
                asyncio.to_thread(
                    load_document, job["pdf_path"], job_id, self.pdf_max_pages
                ),
                timeout=self.pdf_parse_timeout,
            )
            result = await self._run_with_retries(RunContext(document=document), job_id)
            duration = round(perf_counter() - start, 3)

            updated = await self.job_dao.update_status(
                job_id,
                "completed",
                result={
                    "records": [r.model_dump() for r in result.extraction.records],
                    "flagged": [f.model_dump() for f in result.extraction.flagged],
                },
                token_usage=result.token_usage,
                cost_usd=result.cost_usd,
                processing_duration_seconds=duration,
                expected_status="processing",
                expected_attempts=expected_attempts,
            )
            if updated is None:
                self.logger.warning(
                    "terminal_write_skipped",
                    job_id=job_id,
                    intended="completed",
                    reason="job no longer in processing (recovered or re-claimed)",
                )
                return
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
            token_usage, cost_usd = self._usage_on_failure(exc)
            try:
                updated = await self.job_dao.update_status(
                    job_id,
                    "failed",
                    error=f"{type(exc).__name__}: {exc}",
                    token_usage=token_usage,
                    cost_usd=cost_usd,
                    processing_duration_seconds=duration,
                    expected_status="processing",
                    expected_attempts=expected_attempts,
                )
                if updated is None:
                    self.logger.warning(
                        "terminal_write_skipped",
                        job_id=job_id,
                        intended="failed",
                        reason="job no longer in processing (recovered or re-claimed)",
                    )
            except Exception:
                # Last-ditch: never let a status-write failure escape the worker.
                self.logger.exception("job_failed_status_write_error", job_id=job_id)

    def _usage_on_failure(self, exc: BaseException) -> tuple[dict | None, float | None]:
        """Recover token usage/cost from a failed agent run, if the SDK kept it."""
        usage = usage_from_exception(exc)
        if usage is None:
            return None, None
        token_usage = usage_to_token_dict(usage)
        cost = estimate_cost_usd(
            EXTRACTION_AGENT_CONFIG.model,
            input_tokens=token_usage.get("input", 0),
            output_tokens=token_usage.get("output", 0),
            cached_input_tokens=token_usage.get("cached_input", 0),
        )
        return token_usage, cost

    async def _run_with_retries(
        self, ctx: RunContext, job_id: str
    ) -> OrchestratorResult:
        """Run the orchestrator, retrying transient failures with exp. backoff.

        Fatal (non-transient) errors propagate immediately. When all attempts are
        spent on transient errors, raise an error that names what was tried, so it
        lands in the job's ``error`` field.
        """
        last_exc: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                # Bound the model call: a hung request can't hold the worker until
                # the stall-recovery timer. A timeout is transient -> retried below.
                return await asyncio.wait_for(
                    ExtractionOrchestrator().run(ctx), timeout=self.extraction_timeout
                )
            except Exception as exc:
                last_exc = exc
                transient = is_transient(exc)
                if transient and attempt < self.max_attempts:
                    backoff = self.backoff_base * (2 ** (attempt - 1))
                    self.logger.warning(
                        "extraction_retry",
                        job_id=job_id,
                        attempt=attempt,
                        max_attempts=self.max_attempts,
                        backoff_seconds=backoff,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    await asyncio.sleep(backoff)
                    continue
                if transient:
                    raise RuntimeError(
                        f"extraction failed after {self.max_attempts} attempts "
                        f"(transient): {type(exc).__name__}: {exc}"
                    ) from exc
                raise  # fatal — fail fast
        # Unreachable, but keeps the type checker happy.
        raise last_exc if last_exc else RuntimeError("extraction failed")
