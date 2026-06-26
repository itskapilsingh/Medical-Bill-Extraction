from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text, tuple_, update

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
        *,
        result: dict | None = None,
        error: str | None = None,
        token_usage: dict | None = None,
        cost_usd: float | None = None,
        processing_duration_seconds: float | None = None,
        expected_status: str | None = None,
        expected_attempts: int | None = None,
    ) -> dict | None:
        """Update job status and optionally write result/error/metrics.

        ``expected_status`` / ``expected_attempts`` add an optimistic guard to the
        WHERE clause. The worker passes ``expected_status='processing'`` and the
        attempts value it claimed, so a terminal write only lands if THIS run still
        owns the job. If crash-recovery re-queued the job and another worker
        re-claimed it (bumping ``attempts``), the guard fails and the stale run's
        write is a no-op (returns None) instead of clobbering the newer result.

        Returns the updated job as a dict, or None if no row matched (does not
        exist, owned by another user — RLS-invisible — or the guard rejected it).
        """
        values: dict[str, Any] = {"status": status, "updated_at": utc_now()}
        if result is not None:
            values["result"] = result
        if error is not None:
            values["error"] = error
        if token_usage is not None:
            values["token_usage"] = token_usage
        if cost_usd is not None:
            values["cost_usd"] = cost_usd
        if processing_duration_seconds is not None:
            values["processing_duration_seconds"] = processing_duration_seconds
        if status == ACTIVE_STATUS:
            values["started_at"] = utc_now()
        if status in ("completed", "failed", "cancelled"):
            values["completed_at"] = utc_now()

        conditions = [Job.id == job_id]
        if expected_status is not None:
            conditions.append(Job.status == expected_status)
        if expected_attempts is not None:
            conditions.append(Job.attempts == expected_attempts)

        async with self.context_manager.session() as session:
            stmt = update(Job).where(*conditions).values(**values).returning(Job)
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

    async def list(
        self,
        status: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        before: tuple[datetime, str] | None = None,
    ) -> list[dict]:
        """Return the caller's jobs, newest first, optionally filtered/paged.

        Ordering is total — ``(created_at, id)`` descending — so the id breaks
        ties between rows created in the same instant and pagination is stable.

        Two paging modes:

        - ``before`` is a keyset cursor ``(created_at, id)``: returns only rows
          strictly older than it. This is the preferred mode — it is immune to
          rows being inserted at the head between pages (no skipped/duplicated
          rows) and never pays the deep-``OFFSET`` scan cost.
        - ``offset`` is the classic skip count, kept for simple callers.

        ``before`` takes precedence over ``offset`` when both are given. RLS still
        scopes the rows to the caller either way.
        """
        async with self.context_manager.session() as session:
            query = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
            if status is not None:
                query = self._apply_filters(query, {"status": status})
            if before is not None:
                query = query.where(
                    tuple_(Job.created_at, Job.id) < tuple_(before[0], before[1])
                )
            elif offset:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)
            rows = (await session.execute(query)).scalars().all()
            return [self._to_dto(r) for r in rows]

    async def get_active(self) -> list[dict]:
        """Return the caller's jobs currently in processing status."""
        return await self.list(status=ACTIVE_STATUS)

    async def summary(self) -> dict:
        """Aggregate the caller's jobs server-side (RLS-scoped).

        Returns status counts plus record/flag counts and financial totals,
        computed in SQL over EVERY job the caller owns — so the dashboard's
        headline numbers stay correct no matter how many documents exist, instead
        of being summed client-side over a truncated page.
        """
        async with self.context_manager.session() as session:
            counts = (
                await session.execute(
                    text(
                        """
                        SELECT
                          count(*) AS total,
                          count(*) FILTER (WHERE status='completed')  AS completed,
                          count(*) FILTER (WHERE status='processing') AS processing,
                          count(*) FILTER (WHERE status='pending')    AS pending,
                          count(*) FILTER (WHERE status='failed')     AS failed,
                          count(*) FILTER (WHERE status='cancelled')  AS cancelled,
                          COALESCE(SUM(jsonb_array_length(result->'records'))
                              FILTER (WHERE jsonb_typeof(result->'records')='array'), 0) AS records_count,
                          COALESCE(SUM(jsonb_array_length(result->'flagged'))
                              FILTER (WHERE jsonb_typeof(result->'flagged')='array'), 0) AS flagged_count
                        FROM jobs
                        """
                    )
                )
            ).mappings().one()

            fin = (
                await session.execute(
                    text(
                        r"""
                        SELECT
                          COALESCE(SUM(v.total_charges), 0) AS total_charges,
                          COALESCE(SUM(v.ins_paid),      0) AS ins_paid,
                          COALESCE(SUM(v.adjustment),    0) AS adjustment,
                          COALESCE(SUM(v.payments),      0) AS payments,
                          COALESCE(SUM(v.balance),       0) AS balance
                        FROM (
                          SELECT result FROM jobs
                          WHERE status='completed'
                            AND jsonb_typeof(result->'records')='array'
                        ) j
                        CROSS JOIN LATERAL jsonb_array_elements(j.result->'records') AS rec
                        CROSS JOIN LATERAL (
                          SELECT
                            CASE WHEN rec->>'total_charges' ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$'
                                 THEN (rec->>'total_charges')::numeric END AS total_charges,
                            CASE WHEN rec->>'ins_paid' ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$'
                                 THEN (rec->>'ins_paid')::numeric END AS ins_paid,
                            CASE WHEN rec->>'adjustment' ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$'
                                 THEN (rec->>'adjustment')::numeric END AS adjustment,
                            CASE WHEN rec->>'payments' ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$'
                                 THEN (rec->>'payments')::numeric END AS payments,
                            CASE WHEN rec->>'balance' ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$'
                                 THEN (rec->>'balance')::numeric END AS balance
                        ) v
                        """
                    )
                )
            ).mappings().one()

        return {
            "total": int(counts["total"]),
            "completed": int(counts["completed"]),
            "processing": int(counts["processing"]),
            "pending": int(counts["pending"]),
            "failed": int(counts["failed"]),
            "cancelled": int(counts["cancelled"]),
            "records_count": int(counts["records_count"]),
            "flagged_count": int(counts["flagged_count"]),
            "total_charges": float(fin["total_charges"]),
            "ins_paid": float(fin["ins_paid"]),
            "adjustment": float(fin["adjustment"]),
            "payments": float(fin["payments"]),
            "balance": float(fin["balance"]),
        }

    # ----------------------------------------------------- worker queue (M2/M3)

    async def claim_next_job(self) -> dict | None:
        """Atomically claim the next pending job for processing.

        Delegates to the ``claim_next_job()`` SECURITY DEFINER function (see the
        worker-queue migration). The function runs as the table owner, so it can
        see pending jobs across ALL users — the one deliberate cross-user surface
        — and uses ``FOR UPDATE SKIP LOCKED`` so two workers never grab the same
        row. The app role itself still cannot read across users; it only receives
        the single row the function chose to hand back, already flipped to
        ``processing``.

        Returns the claimed job (incl. owner_id, so the worker can then act under
        that identity) or None if the queue is empty.
        """
        async with self.context_manager.session() as session:
            row = (
                await session.execute(text("SELECT * FROM claim_next_job()"))
            ).mappings().first()
            return dict(row) if row is not None else None

    async def recover_stalled(self, timeout_minutes: int, max_attempts: int) -> int:
        """Recover jobs stranded in 'processing' by a crashed worker.

        Delegates to the recover_stalled_jobs() SECURITY DEFINER function so it
        can act across owners. Returns the number of jobs recovered.
        """
        async with self.context_manager.session() as session:
            result = await session.execute(
                text("SELECT recover_stalled_jobs(:t, :m)"),
                {"t": timeout_minutes, "m": max_attempts},
            )
            return int(result.scalar() or 0)

    async def find_active_duplicate(self, content_hash: str) -> dict | None:
        """Return the caller's most recent still-running job with this fingerprint.

        Used to coalesce duplicate uploads: if the same user re-submits identical
        bytes while an earlier job is still ``pending``/``processing``, we hand
        back that job instead of queueing a second identical extraction (and a
        second spend). RLS scopes this to the caller, so it never coalesces across
        users. Returns None if there is no in-flight job for this content.
        """
        if not content_hash:
            return None
        async with self.context_manager.session() as session:
            query = (
                select(Job)
                .where(
                    Job.content_hash == content_hash,
                    Job.status.in_((PENDING_STATUS, ACTIVE_STATUS)),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            orm = (await session.execute(query)).scalar_one_or_none()
            return self._to_dto(orm) if orm is not None else None

    async def find_cached_result(self, content_hash: str) -> dict | None:
        """Return the most recent COMPLETED job (visible to the caller) with this
        content fingerprint, or None.

        RLS scopes the query to the caller's own rows, so a cache hit can never
        reuse another user's result. The caller (POST /jobs) runs with the user's
        identity bound, so no explicit owner filter is needed here.
        """
        if not content_hash:
            return None
        async with self.context_manager.session() as session:
            query = (
                select(Job)
                .where(Job.content_hash == content_hash, Job.status == "completed")
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            orm = (await session.execute(query)).scalar_one_or_none()
            return self._to_dto(orm) if orm is not None else None
