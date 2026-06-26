from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

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
            reusable = await self.create_reusable_job(
                owner_id=owner_id,
                pdf_filename=pdf_filename,
                content_hash=content_hash,
            )
            if reusable is not None:
                return reusable

        async def _insert() -> dict:
            return await self.job_dao.create(
                owner_id=owner_id,
                pdf_filename=pdf_filename,
                pdf_path=pdf_path,
                content_hash=content_hash,
            )

        try:
            job = await _insert()
        except IntegrityError:
            inflight = await self.job_dao.find_active_duplicate(content_hash)
            if inflight is not None:
                self.logger.info(
                    "job_dedup_inflight_race",
                    job_id=inflight["id"],
                    owner_id=owner_id,
                    status=inflight["status"],
                    content_hash=(content_hash or "")[:12],
                )
                return inflight
            # The racing winner already reached a terminal state, so the active-
            # dedup index no longer covers it; a fresh insert now succeeds.
            job = await _insert()

        self.logger.info("job_created", job_id=job["id"], owner_id=owner_id)
        return job

    async def create_reusable_job(
        self,
        *,
        owner_id: str,
        pdf_filename: str,
        content_hash: str | None,
    ) -> dict | None:
        """Return/create a reusable job for duplicate bytes, without a new PDF.

        A completed cache hit creates a new completed row that reuses the cached
        result and the cached job's existing ``pdf_path`` metadata. An in-flight
        duplicate returns the existing active job. In both cases the caller does
        not need to persist a second copy of the same PHI-bearing PDF.
        """
        if not content_hash:
            return None

        cached = await self.job_dao.find_cached_result(content_hash)
        if cached is not None:
            job = await self.job_dao.create(
                owner_id=owner_id,
                pdf_filename=pdf_filename,
                pdf_path=cached["pdf_path"],
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

        return None

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
        before: tuple[datetime, str] | None = None,
    ) -> list[dict]:
        """Return the caller's jobs, newest first, optionally filtered and paged.

        ``before`` is a keyset cursor ``(created_at, id)``; when supplied the page
        is the rows strictly older than it (stable under concurrent head inserts).
        """
        return await self.job_dao.list(
            status=status, limit=limit, offset=offset, before=before
        )

    async def get_active_jobs(self) -> list[dict]:
        """Return the caller's jobs currently being processed (live state)."""
        return await self.job_dao.get_active()

    async def get_summary(self) -> dict:
        """Server-side aggregate of the caller's jobs (counts + financial totals)."""
        return await self.job_dao.summary()

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
