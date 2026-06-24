from __future__ import annotations

from app.core.common.time import utc_now
from app.core.context_manager import ContextManager
from app.dao.pg.job_dao import JobDAO
from app.service.base_service import BaseService
from app.service.exceptions import (
    JobNotCancellableException,
    JobNotFoundException,
)


class JobService(BaseService):
    """Owns the job lifecycle: creation, status queries, and cancellation.

    All database access goes through JobDAO. This service does not interact with
    the AI layer — that is ExtractionService's responsibility. It assumes the
    caller's identity is already bound to the request context (the API auth
    dependency does this), so it never has to thread a user id through reads;
    RLS scopes them.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager)
        self.job_dao = JobDAO(context_manager)

    async def create_job(
        self,
        *,
        owner_id: str,
        pdf_filename: str,
        pdf_path: str,
        content_hash: str | None = None,
        bypass_cache: bool = False,
    ) -> dict:
        """Create a job for ``owner_id``.

        Unless caching is bypassed, if the same user already has a COMPLETED job
        with the same content fingerprint, create a new job immediately in
        ``completed`` status reusing that result + metrics (no reprocessing). The
        cache lookup is RLS-scoped to the caller, so a hit never crosses users.
        """
        if not bypass_cache and content_hash:
            cached = await self.job_dao.find_cached_result(content_hash)
            if cached is not None:
                job = await self.job_dao.create(
                    owner_id=owner_id,
                    pdf_filename=pdf_filename,
                    pdf_path=pdf_path,
                    content_hash=content_hash,
                    status="completed",
                    result=cached["result"],
                    token_usage=cached["token_usage"],
                    cost_usd=cached["cost_usd"],
                    processing_duration_seconds=0.0,
                    completed_at=utc_now(),
                )
                self.logger.info(
                    "job_cache_hit",
                    job_id=job["id"],
                    owner_id=owner_id,
                    content_hash=content_hash[:12],
                )
                return job

            # No completed result yet, but the same bytes may already be in
            # flight for this user — coalesce onto it rather than queue a second
            # identical extraction (and double the spend).
            inflight = await self.job_dao.find_active_duplicate(content_hash)
            if inflight is not None:
                self.logger.info(
                    "job_dedup_inflight",
                    job_id=inflight["id"],
                    owner_id=owner_id,
                    status=inflight["status"],
                    content_hash=content_hash[:12],
                )
                return inflight

        job = await self.job_dao.create(
            owner_id=owner_id,
            pdf_filename=pdf_filename,
            pdf_path=pdf_path,
            content_hash=content_hash,
        )
        self.logger.info("job_created", job_id=job["id"], owner_id=owner_id)
        return job

    async def get_job(self, job_id: str) -> dict:
        """Return a job by ID. Raises JobNotFoundException if not visible.

        "Not visible" covers both "does not exist" and "owned by someone else":
        RLS returns no row in either case, and we surface an identical 404 so a
        job's existence is never leaked across the user boundary.
        """
        job = await self.job_dao.get(job_id)
        if job is None:
            raise JobNotFoundException(job_id)
        return job

    async def list_jobs(
        self,
        status: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Return the caller's jobs, newest first, optionally filtered and paged."""
        return await self.job_dao.list(status=status, limit=limit, offset=offset)

    async def get_active_jobs(self) -> list[dict]:
        """Return the caller's jobs currently being processed (live state)."""
        return await self.job_dao.get_active()

    async def claim_next_job(self) -> dict | None:
        """Claim the next pending job for a worker (no caller identity bound).

        Returns the claimed job (incl. owner_id) or None if the queue is empty.
        See JobDAO.claim_next_job for the concurrency/RLS mechanics.
        """
        return await self.job_dao.claim_next_job()

    async def recover_stalled(self, timeout_minutes: int, max_attempts: int) -> int:
        """Recover jobs stranded in 'processing' by a crashed worker."""
        return await self.job_dao.recover_stalled(timeout_minutes, max_attempts)

    async def cancel_job(self, job_id: str) -> dict:
        """Cancel a pending job the caller owns.

        Raises JobNotFoundException if the job is not visible to the caller, and
        JobNotCancellableException if it is no longer pending. The DAO performs
        the transition atomically (``... WHERE status = 'pending'``), so a job
        claimed by a worker between our check and the update is handled by the
        race fallback rather than being wrongly cancelled.
        """
        job = await self.job_dao.get(job_id)
        if job is None:
            raise JobNotFoundException(job_id)
        if job["status"] != "pending":
            raise JobNotCancellableException(job_id, job["status"])

        cancelled = await self.job_dao.cancel(job_id)
        if not cancelled:
            latest = await self.job_dao.get(job_id)
            current = latest["status"] if latest else "unknown"
            raise JobNotCancellableException(job_id, current)

        return await self.get_job(job_id)
