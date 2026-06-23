"""Worker-queue safety and the process_job lifecycle (happy + unhappy), against a
live Postgres. The extraction LLM is mocked — these test the *plumbing* (safe
claiming, RLS-scoped result writes, terminal states, metrics), not the agent."""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.ai.orchestrator import OrchestratorResult
from app.ai.types import Document, Page
from app.core.identity import acting_as
from app.models.extraction import BillingRecord, ExtractionOutput

_FAKE_DOC = Document(doc_id="t", num_pages=1, pages=[Page(page_num=1, page_content="x")])

pytestmark = pytest.mark.asyncio


async def _seed_pending(
    admin_engine, owner_id: str, n: int, status: str = "pending"
) -> list[str]:
    ids = [f"job-{uuid.uuid4().hex}" for _ in range(n)]
    async with admin_engine.begin() as conn:
        for jid in ids:
            await conn.execute(
                text(
                    "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status, "
                    "started_at) VALUES (:id, :owner, 'x.pdf', '/p/x.pdf', :status, now())"
                ),
                {"id": jid, "owner": owner_id, "status": status},
            )
    return ids


async def test_concurrent_claims_never_double_claim(app_engine, admin_engine, two_users):
    """Fire more concurrent claims than there are jobs: every job is claimed at
    most once (FOR UPDATE SKIP LOCKED), and the surplus claims get nothing."""
    alice, _ = two_users
    seeded = await _seed_pending(admin_engine, alice, 5)
    try:
        async def claim_one():
            async with app_engine.connect() as conn:
                async with conn.begin():
                    row = (
                        await conn.execute(text("SELECT id FROM claim_next_job()"))
                    ).first()
                    return row.id if row else None

        results = await asyncio.gather(*[claim_one() for _ in range(8)])
        claimed = [r for r in results if r is not None]

        assert sorted(claimed) == sorted(seeded)  # all 5, no duplicates
        assert len(claimed) == len(set(claimed)) == 5
        assert results.count(None) == 3
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM jobs WHERE id = ANY(:ids)"), {"ids": seeded}
            )


async def test_process_job_writes_result_and_metrics(
    context_manager, admin_engine, two_users, monkeypatch
):
    """Happy path: a claimed job ends 'completed' with records + metrics, written
    under the owner's RLS identity."""
    from app.service.extraction_service import ExtractionService
    import app.service.extraction_service as svc_module

    alice, _ = two_users
    (job_id,) = await _seed_pending(admin_engine, alice, 1, status="processing")

    canned = OrchestratorResult(
        extraction=ExtractionOutput(
            records=[
                BillingRecord(
                    treatment_date="01/04/2024",
                    cpt_codes=["99213"],
                    provider="Test Clinic",
                    total_charges=100.0,
                    page="1",
                )
            ],
            flagged=[],
        ),
        model="gpt-5.4-mini",
        token_usage={"input": 10, "output": 5, "total": 15},
        cost_usd=0.0001,
        agent_seconds=0.2,
    )

    monkeypatch.setattr(svc_module, "load_document", lambda path, doc_id: _FAKE_DOC)

    class FakeOrchestrator:
        async def run(self, ctx):
            return canned

    monkeypatch.setattr(svc_module, "ExtractionOrchestrator", FakeOrchestrator)

    service = ExtractionService(context_manager)
    with acting_as(alice):
        await service.process_job(job_id)

    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT status, result, token_usage, cost_usd, "
                    "processing_duration_seconds FROM jobs WHERE id = :id"
                ),
                {"id": job_id},
            )
        ).first()
    assert row.status == "completed"
    assert row.result["records"][0]["provider"] == "Test Clinic"
    assert row.token_usage["total"] == 15
    assert row.cost_usd == 0.0001
    assert row.processing_duration_seconds is not None

    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job_id})


async def test_process_job_failure_marks_failed_and_never_raises(
    context_manager, admin_engine, two_users, monkeypatch
):
    """Unhappy path: extraction blowing up ends the job 'failed' with an error
    message, and process_job itself does not raise (worker stays alive)."""
    import app.service.extraction_service as svc_module
    from app.service.extraction_service import ExtractionService

    alice, _ = two_users
    (job_id,) = await _seed_pending(admin_engine, alice, 1, status="processing")

    def boom(path, doc_id):
        raise RuntimeError("corrupt PDF")

    monkeypatch.setattr(svc_module, "load_document", boom)

    service = ExtractionService(context_manager)
    with acting_as(alice):
        await service.process_job(job_id)  # must not raise

    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, error FROM jobs WHERE id = :id"), {"id": job_id}
            )
        ).first()
    assert row.status == "failed"
    assert "corrupt PDF" in row.error

    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job_id})
