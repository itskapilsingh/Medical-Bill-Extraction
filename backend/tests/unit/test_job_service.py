"""JobService lifecycle rules, exercised against a fake DAO (no database)."""

from types import SimpleNamespace

import pytest

from app.service.exceptions import (
    JobNotCancellableException,
    JobNotFoundException,
)
from app.service.job_service import JobService

pytestmark = pytest.mark.asyncio


class FakeJobDAO:
    """Minimal stand-in: scripted get() results and a cancel() outcome."""

    def __init__(self, get_results, cancel_result=False, created=None):
        self._get_results = list(get_results)
        self._cancel_result = cancel_result
        self._created = created
        self.cancel_calls = 0

    async def get(self, job_id):
        if len(self._get_results) > 1:
            return self._get_results.pop(0)
        return self._get_results[0] if self._get_results else None

    async def cancel(self, job_id):
        self.cancel_calls += 1
        return self._cancel_result

    async def create(self, **kwargs):
        return self._created


def make_service(dao: FakeJobDAO) -> JobService:
    service = JobService(SimpleNamespace())  # context_manager is unused by the fake
    service.job_dao = dao
    return service


async def test_get_missing_job_raises_not_found():
    service = make_service(FakeJobDAO(get_results=[None]))
    with pytest.raises(JobNotFoundException):
        await service.get_job("nope")


async def test_cancel_missing_job_raises_not_found():
    service = make_service(FakeJobDAO(get_results=[None]))
    with pytest.raises(JobNotFoundException):
        await service.cancel_job("nope")


async def test_cancel_processing_job_raises_conflict():
    service = make_service(
        FakeJobDAO(get_results=[{"id": "j", "status": "processing"}])
    )
    with pytest.raises(JobNotCancellableException):
        await service.cancel_job("j")


async def test_cancel_completed_job_raises_conflict():
    service = make_service(
        FakeJobDAO(get_results=[{"id": "j", "status": "completed"}])
    )
    with pytest.raises(JobNotCancellableException):
        await service.cancel_job("j")


async def test_cancel_pending_job_succeeds():
    dao = FakeJobDAO(
        get_results=[
            {"id": "j", "status": "pending"},  # pre-check
            {"id": "j", "status": "cancelled"},  # after cancel
        ],
        cancel_result=True,
    )
    service = make_service(dao)
    result = await service.cancel_job("j")
    assert result["status"] == "cancelled"
    assert dao.cancel_calls == 1


async def test_cancel_loses_race_with_worker_raises_conflict():
    # get() says pending, but cancel() returns False (a worker claimed it first).
    dao = FakeJobDAO(
        get_results=[
            {"id": "j", "status": "pending"},
            {"id": "j", "status": "processing"},
        ],
        cancel_result=False,
    )
    service = make_service(dao)
    with pytest.raises(JobNotCancellableException):
        await service.cancel_job("j")
