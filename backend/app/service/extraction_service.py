from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from time import perf_counter

from app.ai.config import EXTRACTION_AGENT_CONFIG
from app.ai.context import RunContext
from app.ai.metrics import usage_from_exception, usage_to_token_dict
from app.ai.orchestrator import ExtractionOrchestrator, OrchestratorResult
from app.ai.pdf_loader import VisionExtractionRequired, load_document
from app.ai.pdf_vision_extractor import PdfVisionExtractor
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
        self.pdf_mount_path = settings.PDF_MOUNT_PATH

    _ERROR_MAX_LEN = 500

    def _format_error(self, exc: BaseException) -> str:
        """Build the client-facing error string for a failed job.

        Redacts the on-disk PDF location so internal filesystem paths don't leak
        into the API response, and caps the length so a hostile input can't stuff
        the job row (and every response that returns it) with a huge message.
        """
        msg = f"{type(exc).__name__}: {exc}"
        if self.pdf_mount_path:
            msg = msg.replace(self.pdf_mount_path, "<pdf-volume>")
        if len(msg) > self._ERROR_MAX_LEN:
            msg = msg[: self._ERROR_MAX_LEN - 1] + "…"
        return msg

    async def process_job(self, job_id: str, expected_attempts: int | None = None) -> None:
        """Run the full extraction pipeline for an already-claimed job.

        ``expected_attempts`` is the attempts value the worker claimed; it guards
        the terminal write so a run that was recovered out from under us (crash
        recovery re-queued the job and another worker re-claimed it) cannot
        overwrite the newer run's result.
        """
        start = perf_counter()
        job: dict | None = None
        try:
            job = await self.job_dao.get(job_id)
            if job is None:
                # RLS-invisible or already gone — nothing safe to do.
                self.logger.warning("process_job_not_visible", job_id=job_id)
                return

            content_hash = job.get("content_hash")
            if content_hash:
                cached = await self.job_dao.find_cached_result(content_hash)
                if cached is not None and cached["id"] != job_id:
                    duration = round(perf_counter() - start, 3)
                    updated = await self.job_dao.update_status(
                        job_id,
                        "completed",
                        result=cached["result"],
                        token_usage=cached["token_usage"],
                        cost_usd=cached["cost_usd"],
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
                    self._delete_pdf(job_id, job["pdf_path"])
                    self.logger.info(
                        "job_completed_from_cache", job_id=job_id, source_job=cached["id"]
                    )
                    return

            try:
                document = await asyncio.wait_for(
                    asyncio.to_thread(
                        load_document, job["pdf_path"], job_id, self.pdf_max_pages
                    ),
                    timeout=self.pdf_parse_timeout,
                )
            except VisionExtractionRequired as exc:
                self.logger.info(
                    "pdf_vision_fallback_required",
                    job_id=job_id,
                    pages=exc.pages,
                    reason=str(exc),
                )
                result = await self._run_pdf_vision_with_retries(
                    job["pdf_path"], job_id
                )
            else:
                result = await self._run_with_retries(
                    RunContext(document=document), job_id
                )
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
            self._delete_pdf(job_id, job["pdf_path"])
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
                    error=self._format_error(exc),
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
                elif job is not None:
                    # Terminal failure: the PDF won't be reprocessed, so drop it.
                    self._delete_pdf(job_id, job["pdf_path"])
            except Exception:
                # Last-ditch: never let a status-write failure escape the worker.
                self.logger.exception("job_failed_status_write_error", job_id=job_id)

    def _delete_pdf(self, job_id: str, pdf_path: str | None) -> None:
        """Remove the source PDF from the volume once the job is terminal.

        Best-effort PHI minimization: the extracted records are persisted in the
        DB, so the raw document is no longer needed. Never raises — a cleanup
        failure must not turn a finished job into a failed one. No-op when the
        feature is disabled or the path is empty.
        """
        if not self.delete_pdf_after or not pdf_path:
            return
        try:
            os.remove(pdf_path)
            self.logger.info("pdf_deleted", job_id=job_id)
        except FileNotFoundError:
            pass  # already gone (cache hit reusing a path, or a prior sweep)
        except OSError:
            self.logger.warning("pdf_delete_failed", job_id=job_id)

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
        return await self._run_operation_with_retries(
            lambda: ExtractionOrchestrator().run(ctx), job_id
        )

    async def _run_pdf_vision_with_retries(
        self, pdf_path: str, job_id: str
    ) -> OrchestratorResult:
        return await self._run_operation_with_retries(
            lambda: PdfVisionExtractor().run(pdf_path=pdf_path, job_id=job_id), job_id
        )

    async def _run_operation_with_retries(
        self,
        operation: Callable[[], Awaitable[OrchestratorResult]],
        job_id: str,
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
                    operation(), timeout=self.extraction_timeout
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
