"""Unit coverage for the extraction service's reliability + PHI logic.

These exercise the parts that don't need a live model or database: the
retry/backoff state machine, the failure-message redaction, and the post-job
PDF deletion. The orchestrator is stubbed so we control its outcomes.
"""

import asyncio

import pytest

import app.service.extraction_service as svc_mod
from app.ai.orchestrator import OrchestratorResult
from app.ai.pdf_loader import VisionExtractionRequired
from app.models.extraction import BillingRecord, ExtractionOutput
from app.service.extraction_service import ExtractionService


# Class name is in retry._TRANSIENT_NAMES, so is_transient() treats it as retryable.
class RateLimitError(Exception):
    pass


def _service() -> ExtractionService:
    # BaseService/JobDAO only stash the context manager; nothing connects here.
    svc = ExtractionService(context_manager=object())
    svc.backoff_base = 0  # no real waiting in tests
    return svc


def _stub_orchestrator(monkeypatch, outcomes):
    """Replace ExtractionOrchestrator with one that yields `outcomes` in order.

    Each outcome is either an Exception (raised) or an OrchestratorResult.
    """
    calls = {"n": 0}

    class _Fake:
        async def run(self, ctx):
            i = calls["n"]
            calls["n"] += 1
            result = outcomes[i]
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(svc_mod, "ExtractionOrchestrator", _Fake)
    return calls


@pytest.mark.asyncio
async def test_retries_transient_then_succeeds(monkeypatch):
    svc = _service()
    ok = OrchestratorResult()
    calls = _stub_orchestrator(monkeypatch, [RateLimitError("429"), ok])

    result = await svc._run_with_retries(ctx=None, job_id="j1")

    assert result is ok
    assert calls["n"] == 2  # one failure + one success


@pytest.mark.asyncio
async def test_fatal_error_is_not_retried(monkeypatch):
    svc = _service()
    calls = _stub_orchestrator(monkeypatch, [ValueError("corrupt pdf"), OrchestratorResult()])

    with pytest.raises(ValueError):
        await svc._run_with_retries(ctx=None, job_id="j2")
    assert calls["n"] == 1  # fatal fails fast, no second attempt


@pytest.mark.asyncio
async def test_exhausts_attempts_on_persistent_transient(monkeypatch):
    svc = _service()
    svc.max_attempts = 3
    calls = _stub_orchestrator(monkeypatch, [RateLimitError("x")] * 3)

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        await svc._run_with_retries(ctx=None, job_id="j3")
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_timeout_is_transient_and_retried(monkeypatch):
    svc = _service()
    ok = OrchestratorResult()
    calls = _stub_orchestrator(monkeypatch, [asyncio.TimeoutError(), ok])

    result = await svc._run_with_retries(ctx=None, job_id="j4")
    assert result is ok
    assert calls["n"] == 2


def test_format_error_redacts_mount_path_and_truncates():
    svc = _service()
    svc.pdf_mount_path = "/app/pdfs"

    msg = svc._format_error(FileNotFoundError("/app/pdfs/u/secret.pdf missing"))
    assert "/app/pdfs" not in msg
    assert "<pdf-volume>" in msg

    long = svc._format_error(ValueError("z" * 1000))
    assert len(long) <= svc._ERROR_MAX_LEN
    assert long.endswith("…")


def test_delete_pdf_removes_file_when_enabled(tmp_path):
    svc = _service()
    svc.delete_pdf_after = True
    f = tmp_path / "bill.pdf"
    f.write_bytes(b"%PDF-1.4")

    svc._delete_pdf("j5", str(f))
    assert not f.exists()


def test_delete_pdf_noop_when_disabled(tmp_path):
    svc = _service()
    svc.delete_pdf_after = False
    f = tmp_path / "bill.pdf"
    f.write_bytes(b"%PDF-1.4")

    svc._delete_pdf("j6", str(f))
    assert f.exists()


def test_delete_pdf_tolerates_missing_file(tmp_path):
    svc = _service()
    svc.delete_pdf_after = True
    # Must not raise even though the file isn't there.
    svc._delete_pdf("j7", str(tmp_path / "gone.pdf"))


@pytest.mark.asyncio
async def test_process_job_routes_vision_required_pdf_to_pdf_fallback(monkeypatch):
    svc = _service()
    svc.delete_pdf_after = False
    updates = []

    class FakeJobDAO:
        async def get(self, job_id):
            return {"id": job_id, "pdf_path": "/pdfs/scan.pdf"}

        async def update_status(self, job_id, status, **kwargs):
            updates.append({"job_id": job_id, "status": status, **kwargs})
            return {"id": job_id, "status": status}

    def needs_vision(path, doc_id, max_pages=None):
        raise VisionExtractionRequired(
            "PDF has no extractable text; OpenAI PDF vision fallback required",
            pages=[1],
        )

    class FakeVisionExtractor:
        calls = []

        async def run(self, *, pdf_path, job_id):
            self.calls.append({"pdf_path": pdf_path, "job_id": job_id})
            return OrchestratorResult(
                extraction=ExtractionOutput(
                    records=[
                        BillingRecord(
                            invoice_number="INV-200",
                            treatment_date="02/01/2024",
                            cpt_codes=[],
                            provider="Scanned Clinic",
                            total_charges=200.0,
                            page="1",
                        )
                    ]
                ),
                model="gpt-5.4-mini",
                token_usage={"input": 20, "output": 10, "total": 30},
                cost_usd=0.0002,
            )

    svc.job_dao = FakeJobDAO()
    monkeypatch.setattr(svc_mod, "load_document", needs_vision)
    monkeypatch.setattr(svc_mod, "PdfVisionExtractor", FakeVisionExtractor)

    await svc.process_job("job-scan", expected_attempts=1)

    assert FakeVisionExtractor.calls == [
        {"pdf_path": "/pdfs/scan.pdf", "job_id": "job-scan"}
    ]
    assert updates[0]["status"] == "completed"
    assert updates[0]["result"]["records"][0]["invoice_number"] == "INV-200"
    assert updates[0]["token_usage"]["total"] == 30
