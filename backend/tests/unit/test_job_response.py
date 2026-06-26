from datetime import datetime, timezone

from app.api.schema.job import JobResponse


def _base_job(**overrides):
    job = {
        "id": "job-1",
        "owner_id": "user-1",
        "status": "completed",
        "pdf_path": "/app/pdfs/user-1/abc.pdf",
        "content_hash": "deadbeef",
        "result": None,
        "error": None,
        "token_usage": None,
        "cost_usd": None,
        "processing_duration_seconds": None,
        "attempts": 0,
        "started_at": None,
        "completed_at": None,
        "created_at": datetime(2026, 6, 22, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 22, tzinfo=timezone.utc),
    }
    job.update(overrides)
    return job


def test_records_and_flagged_are_lifted_from_result():
    job = _base_job(
        result={
            "records": [
                {
                    "invoice_number": "INV-100",
                    "treatment_date": "01/04/2024",
                    "cpt_codes": ["99213"],
                    "provider": "Newton Rehabilitation Center",
                    "insurers": ["Molina Healthcare"],
                    "total_charges": 493.2,
                    "ins_paid": 317.79,
                    "page": "1",
                }
            ],
            "flagged": [
                {
                    "row": None,
                    "fields": ["balance"],
                    "reason": "ambiguous",
                    "page": "2",
                    "severity": "low",
                }
            ],
        },
        token_usage={"input": 100, "output": 50, "total": 150},
        cost_usd=0.0123,
        processing_duration_seconds=12.5,
    )
    resp = JobResponse.from_job(job)
    assert resp.job_id == "job-1"
    assert resp.status == "completed"
    assert len(resp.records) == 1
    assert resp.records[0].invoice_number == "INV-100"
    assert resp.records[0].provider == "Newton Rehabilitation Center"
    assert resp.records[0].cpt_codes == ["99213"]
    assert len(resp.flagged) == 1
    assert resp.flagged[0].severity == "low"
    assert resp.token_usage is not None and resp.token_usage.total == 150
    assert resp.cost_usd == 0.0123


def test_null_result_yields_empty_lists_and_null_metrics():
    resp = JobResponse.from_job(_base_job(status="pending"))
    assert resp.records == []
    assert resp.flagged == []
    assert resp.token_usage is None
    assert resp.cost_usd is None


def test_failed_job_surfaces_error():
    resp = JobResponse.from_job(_base_job(status="failed", error="worker exploded"))
    assert resp.status == "failed"
    assert resp.error == "worker exploded"
