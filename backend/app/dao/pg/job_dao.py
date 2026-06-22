from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from app.core.common.time import utc_now
from app.core.context_manager import ContextManager
from app.dao.base_pg_dao import BasePgDAO
from app.dao.models.job import Job

# Terminal / live statuses, kept here so the service layer and SQL agree.
ACTIVE_STATUS = "processing"
PENDING_STATUS = "pending"


class JobDAO(BasePgDAO[Job]):
    """Data access for the jobs table.

    All SQL lives here. No business logic — status-transition *rules* belong in
    JobService. Every method runs through ``context_manager.session()``, which
    stamps the caller's identity onto the transaction, so the SELECTs below
    intentionally do **not** add an ``owner_id`` filter: Row-Level Security is
    the thing that scopes them. That is the property the isolation test checks —
    a row owned by another user is invisible here even with no WHERE clause.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        super().__init__(context_manager, Job)

    # ------------------------------------------------------------------ mapping

    def _to_orm(self, data: dict) -> Job:
        return Job(**data)

    def _to_dto(self, orm: Job) -> dict:
        return {
            "id": orm.id,
            "owner_id": orm.owner_id,
            "pdf_filename": orm.pdf_filename,
            "pdf_path": orm.pdf_path,
            "status": orm.status,
            "content_hash": orm.content_hash,
            "result": orm.result,
            "error": orm.error,
            "token_usage": orm.token_usage,
            "cost_usd": orm.cost_usd,
            "processing_duration_seconds": orm.processing_duration_seconds,
            "attempts": orm.attempts,
            "started_at": orm.started_at,
            "completed_at": orm.completed_at,
            "created_at": orm.created_at,
            "updated_at": orm.updated_at,
        }

    def _apply_filters(self, query: Any, filters: dict) -> Any:
        status = filters.get("status")
        if status is not None:
            query = query.where(Job.status == status)
        return query

    # ------------------------------------------------------------------- writes

    async def create(
        self,
        *,
        owner_id: str,
        pdf_filename: str,
        pdf_path: str,
        content_hash: str | None = None,
        status: str = PENDING_STATUS,
        result: dict | None = None,
        token_usage: dict | None = None,
        cost_usd: float | None = None,
        processing_duration_seconds: float | None = None,
        completed_at: Any | None = None,
    ) -> dict:
        """Insert a new job. ``owner_id`` must be the authenticated user.

        RLS's WITH CHECK clause rejects the INSERT if ``owner_id`` does not match
        the transaction's ``app.user_id``, so a bug that set the wrong owner
        fails loudly instead of creating a cross-user row.
        """
        orm = self._to_orm(
            {
                "owner_id": owner_id,
                "pdf_filename": pdf_filename,
                "pdf_path": pdf_path,
                "content_hash": content_hash,
                "status": status,
                "result": result,
                "token_usage": token_usage,
                "cost_usd": cost_usd,
                "processing_duration_seconds": processing_duration_seconds,
                "completed_at": completed_at,
            }
        )
        created = await self._create(orm)
        return self._to_dto(created)

    async def update_status(
        self,
        job_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> dict | None:
        """Update job status and optionally write result or error.

        Returns the updated job as a dict, or None if no row was visible/updated
        (either the job does not exist or it belongs to another user — RLS makes
        those two cases indistinguishable, which is the point).
        """
        values: dict[str, Any] = {"status": status, "updated_at": utc_now()}
        if result is not None:
            values["result"] = result
        if error is not None:
            values["error"] = error
        if status == ACTIVE_STATUS:
            values["started_at"] = utc_now()
        if status in ("completed", "failed", "cancelled"):
            values["completed_at"] = utc_now()

        async with self.context_manager.session() as session:
            stmt = (
                update(Job)
                .where(Job.id == job_id)
                .values(**values)
                .returning(Job)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_dto(row) if row is not None else None

    async def cancel(self, job_id: str) -> bool:
        """Set a pending job to cancelled.

        Returns True if a pending row was transitioned, False otherwise. The
        ``status = 'pending'`` predicate makes this a safe no-op for jobs already
        picked up by a worker, and RLS makes it a no-op for other users' jobs.
        """
        async with self.context_manager.session() as session:
            stmt = (
                update(Job)
                .where(Job.id == job_id, Job.status == PENDING_STATUS)
                .values(status="cancelled", completed_at=utc_now(), updated_at=utc_now())
                .returning(Job.id)
            )
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    # -------------------------------------------------------------------- reads

    async def get(self, job_id: str) -> dict | None:
        """Return a job by ID, or None if not found / not owned by the caller."""
        orm = await self._get_by_id(job_id)
        return self._to_dto(orm) if orm is not None else None

    async def list(self, status: str | None = None) -> list[dict]:
        """Return the caller's jobs, newest first, optionally filtered by status."""
        async with self.context_manager.session() as session:
            query = select(Job).order_by(Job.created_at.desc())
            if status is not None:
                query = self._apply_filters(query, {"status": status})
            rows = (await session.execute(query)).scalars().all()
            return [self._to_dto(r) for r in rows]

    async def get_active(self) -> list[dict]:
        """Return the caller's jobs currently in processing status."""
        return await self.list(status=ACTIVE_STATUS)

    # ----------------------------------------------------- worker queue (M2/M3)

    async def claim_next_job(self) -> dict | None:
        """Atomically claim the next pending job for processing.

        Implemented in M2 via a SECURITY DEFINER function so the worker can pull
        across all owners' pending jobs from the single queue without the app
        role itself being able to read across users.
        """
        raise NotImplementedError("Worker claiming is implemented in M2.")

    async def recover_stalled(self, timeout_minutes: int = 5) -> int:
        """Reset jobs stuck in processing back to pending (crash recovery, M3)."""
        raise NotImplementedError("Crash recovery is implemented in M3.")
