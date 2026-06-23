"""M3 reliability: content-based caching, crash recovery, and retry behaviour,
against a live Postgres. Extraction is mocked — these test the reliability
plumbing, not the agent."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.ai.orchestrator import OrchestratorResult
from app.ai.types import Document, Page
from app.core.identity import acting_as
from app.dao.pg.job_dao import JobDAO
from app.models.extraction import BillingRecord, ExtractionOutput

pytestmark = pytest.mark.asyncio

_FAKE_DOC = Document(doc_id="t", num_pages=1, pages=[Page(page_num=1, page_content="x")])
_CACHED_RESULT = {"records": [{"provider": "Cached Clinic"}], "flagged": []}


async def _seed_completed(context_manager, owner_id, content_hash):
    """Create a completed job (as the owner) the cache can later reuse."""
    with acting_as(owner_id):
        return await JobDAO(context_manager).create(
            owner_id=owner_id,
            pdf_filename="orig.pdf",
            pdf_path="/p/orig.pdf",
            content_hash=content_hash,
            status="completed",
            result=_CACHED_RESULT,
            token_usage={"input": 100, "output": 50, "total": 150},
            cost_usd=0.0123,
        )


# --------------------------------------------------------------------- caching

async def test_cache_hit_reuses_result_for_same_user(context_manager, two_users):
    from app.service.job_service import JobService

    alice, _ = two_users
    digest = "h" + uuid.uuid4().hex
    await _seed_completed(context_manager, alice, digest)

    service = JobService(context_manager)
    with acting_as(alice):
        job = await service.create_job(
            owner_id=alice, pdf_filename="again.pdf", pdf_path="/p/again.pdf",
            content_hash=digest,
        )
    assert job["status"] == "completed"
    assert job["result"]["records"][0]["provider"] == "Cached Clinic"
    assert job["cost_usd"] == 0.0123
    assert job["processing_duration_seconds"] == 0.0  # no reprocessing


async def test_bypass_flag_forces_fresh_job(context_manager, two_users):
    from app.service.job_service import JobService

    alice, _ = two_users
    digest = "h" + uuid.uuid4().hex
    await _seed_completed(context_manager, alice, digest)

    service = JobService(context_manager)
    with acting_as(alice):
        job = await service.create_job(
            owner_id=alice, pdf_filename="again.pdf", pdf_path="/p/again.pdf",
            content_hash=digest, bypass_cache=True,
        )
    assert job["status"] == "pending"  # fresh, not a cache hit


async def test_cache_never_crosses_users(context_manager, two_users):
    from app.service.job_service import JobService

    alice, bob = two_users
    digest = "h" + uuid.uuid4().hex
    await _seed_completed(context_manager, alice, digest)  # alice has it completed

    service = JobService(context_manager)
    with acting_as(bob):  # bob uploads identical content
        job = await service.create_job(
            owner_id=bob, pdf_filename="same.pdf", pdf_path="/p/same.pdf",
            content_hash=digest,
        )
    # RLS hides alice's completed job from bob, so no cache hit.
    assert job["status"] == "pending"


# ------------------------------------------------------------- crash recovery

async def _insert_processing(admin_engine, owner_id, *, minutes_ago, attempts):
    jid = f"job-{uuid.uuid4().hex}"
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status, "
                "attempts, started_at) VALUES (:id, :o, 'a.pdf', '/p', 'processing', "
                ":att, now() - make_interval(mins => :m))"
            ),
            {"id": jid, "o": owner_id, "att": attempts, "m": minutes_ago},
        )
    return jid


async def _status(admin_engine, jid):
    async with admin_engine.connect() as conn:
        return (
            await conn.execute(text("SELECT status FROM jobs WHERE id = :id"), {"id": jid})
        ).scalar()


async def test_stalled_job_with_retries_left_goes_back_to_pending(
    context_manager, admin_engine, two_users
):
    from app.service.job_service import JobService

    alice, _ = two_users
    jid = await _insert_processing(admin_engine, alice, minutes_ago=10, attempts=1)
    recovered = await JobService(context_manager).recover_stalled(5, 3)
    assert recovered >= 1
    assert await _status(admin_engine, jid) == "pending"


async def test_stalled_job_out_of_retries_is_failed(
    context_manager, admin_engine, two_users
):
    from app.service.job_service import JobService

    alice, _ = two_users
    jid = await _insert_processing(admin_engine, alice, minutes_ago=10, attempts=3)
    await JobService(context_manager).recover_stalled(5, 3)
    assert await _status(admin_engine, jid) == "failed"


async def test_recent_processing_job_is_not_touched(
    context_manager, admin_engine, two_users
):
    from app.service.job_service import JobService

    alice, _ = two_users
    jid = await _insert_processing(admin_engine, alice, minutes_ago=0, attempts=1)
    await JobService(context_manager).recover_stalled(5, 3)
    assert await _status(admin_engine, jid) == "processing"  # within timeout


# -------------------------------------------------------------------- retries

class RateLimitError(Exception):
    """Class name matches what is_transient() treats as retryable."""


def _canned():
    return OrchestratorResult(
        extraction=ExtractionOutput(
            records=[BillingRecord(treatment_date="01/01/2024", provider="P", page="1")]
        ),
        token_usage={"input": 1, "output": 1, "total": 2},
        cost_usd=0.0,
    )


async def _seed_processing_job(admin_engine, owner_id, attempts: int = 1):
    """Seed a job already claimed (status=processing), as the worker would leave
    it before process_job runs."""
    jid = f"job-{uuid.uuid4().hex}"
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO jobs (id, owner_id, pdf_filename, pdf_path, status, "
                "attempts, started_at) VALUES (:id, :o, 'a.pdf', '/p/a.pdf', "
                "'processing', :att, now())"
            ),
            {"id": jid, "o": owner_id, "att": attempts},
        )
    return jid


def _make_service(context_manager, svc_module, run_impl, monkeypatch):
    from app.service.extraction_service import ExtractionService

    monkeypatch.setattr(svc_module, "load_document", lambda path, doc_id: _FAKE_DOC)

    class FakeOrchestrator:
        async def run(self, ctx):
            return await run_impl()

    monkeypatch.setattr(svc_module, "ExtractionOrchestrator", FakeOrchestrator)
    service = ExtractionService(context_manager)
    service.backoff_base = 0  # no real sleeping in tests
    service.max_attempts = 3
    return service


async def test_transient_failures_are_retried_then_succeed(
    context_manager, admin_engine, two_users, monkeypatch
):
    import app.service.extraction_service as svc_module

    alice, _ = two_users
    jid = await _seed_processing_job(admin_engine, alice)

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError("rate limited")
        return _canned()

    service = _make_service(context_manager, svc_module, flaky, monkeypatch)
    with acting_as(alice):
        await service.process_job(jid)

    assert calls["n"] == 3
    assert await _status(admin_engine, jid) == "completed"


async def test_exhausted_retries_end_failed(
    context_manager, admin_engine, two_users, monkeypatch
):
    import app.service.extraction_service as svc_module

    alice, _ = two_users
    jid = await _seed_processing_job(admin_engine, alice)

    async def always_rate_limited():
        raise RateLimitError("still rate limited")

    service = _make_service(context_manager, svc_module, always_rate_limited, monkeypatch)
    with acting_as(alice):
        await service.process_job(jid)

    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, error FROM jobs WHERE id = :id"), {"id": jid}
            )
        ).first()
    assert row.status == "failed"
    assert "after 3 attempts" in row.error


async def test_fatal_error_fails_without_retrying(
    context_manager, admin_engine, two_users, monkeypatch
):
    import app.service.extraction_service as svc_module

    alice, _ = two_users
    jid = await _seed_processing_job(admin_engine, alice)

    calls = {"n": 0}

    async def fatal():
        calls["n"] += 1
        raise ValueError("corrupt content")

    service = _make_service(context_manager, svc_module, fatal, monkeypatch)
    with acting_as(alice):
        await service.process_job(jid)

    assert calls["n"] == 1  # not retried
    assert await _status(admin_engine, jid) == "failed"


# ------------------------------------------------- terminal-write guard / metrics

async def test_stale_run_cannot_clobber_after_reclaim(
    context_manager, admin_engine, two_users, monkeypatch
):
    """A run whose claimed attempts no longer match the row (it was recovered and
    re-claimed) must NOT write its terminal result — the guard rejects it."""
    import app.service.extraction_service as svc_module

    alice, _ = two_users
    jid = await _seed_processing_job(admin_engine, alice, attempts=1)

    async def succeed():
        return _canned()

    service = _make_service(context_manager, svc_module, succeed, monkeypatch)
    with acting_as(alice):
        # This run thinks it claimed attempts=99, but the row has attempts=1.
        await service.process_job(jid, expected_attempts=99)

    # Guard blocked the write — the job is untouched, not clobbered to completed.
    assert await _status(admin_engine, jid) == "processing"


async def test_failed_job_persists_usage_recovered_from_exception(
    context_manager, admin_engine, two_users, monkeypatch
):
    """A terminal agent failure that carries usage (e.g. max-turns) should still
    surface token_usage/cost on the failed job."""
    import app.service.extraction_service as svc_module

    alice, _ = two_users
    jid = await _seed_processing_job(admin_engine, alice, attempts=1)

    class MaxTurnsExceeded(Exception):
        pass

    async def blow_up_with_usage():
        exc = MaxTurnsExceeded("max turns")
        exc.run_data = SimpleNamespace(
            context_wrapper=SimpleNamespace(
                usage=SimpleNamespace(input_tokens=200, output_tokens=50, total_tokens=250)
            )
        )
        raise exc

    service = _make_service(context_manager, svc_module, blow_up_with_usage, monkeypatch)
    with acting_as(alice):
        await service.process_job(jid, expected_attempts=1)

    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, token_usage, cost_usd FROM jobs WHERE id = :id"),
                {"id": jid},
            )
        ).first()
    assert row.status == "failed"
    assert row.token_usage["total"] == 250
    assert row.cost_usd is not None and row.cost_usd > 0
