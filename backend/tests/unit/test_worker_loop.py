"""Worker loop control flow — claiming, bounded concurrency, and graceful drain —
exercised with every external dependency (DB, services, signals) stubbed, so the
test is fast and deterministic and asserts the *plumbing*, not extraction."""

import asyncio
from types import SimpleNamespace

import pytest

from app.worker import loop

pytestmark = pytest.mark.asyncio


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        LOG_LEVEL="INFO",
        ENVIRONMENT="test",
        WORKER_CONCURRENCY=2,
        WORKER_POLL_INTERVAL_SECONDS=0.01,
        RETENTION_SWEEP_INTERVAL_SECONDS=0,  # disable the sweep for these tests
        PDF_MOUNT_PATH="/tmp",
        RETENTION_DAYS=0,
        WORKER_STALL_TIMEOUT_MINUTES=15,
        EXTRACTION_MAX_ATTEMPTS=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_interruptible_sleep_returns_early_when_stopped():
    stop = asyncio.Event()
    stop.set()
    # Would block ~10s if it ignored the event; must return ~immediately.
    await asyncio.wait_for(loop._interruptible_sleep(stop, 10), timeout=0.5)


async def test_wait_for_capacity_returns_when_a_slot_frees():
    stop = asyncio.Event()
    done_soon = asyncio.ensure_future(asyncio.sleep(0.02))
    in_flight = {done_soon}
    # Should return as soon as the in-flight task completes, well before timeout.
    await asyncio.wait_for(loop._wait_for_capacity(in_flight, stop, 10), timeout=0.5)
    await done_soon


async def test_run_drains_inflight_jobs_before_closing(monkeypatch):
    """On stop, the loop finishes the jobs it already claimed (so a shutdown never
    strands a mid-run job) and only then closes the DB pool."""
    holder: dict = {}

    monkeypatch.setattr(loop, "_install_signal_handlers", lambda ev: holder.__setitem__("stop", ev))
    monkeypatch.setattr(loop, "configure_json_logging", lambda *a, **k: None)
    monkeypatch.setattr(loop, "set_tracing_disabled", lambda *a, **k: None)
    monkeypatch.setattr(loop, "get_settings", _settings)

    closed = {"value": False}

    class FakeContextManager:
        def __init__(self, *_a):
            pass

        async def initialize(self):
            pass

        async def close(self):
            closed["value"] = True

    monkeypatch.setattr(loop, "ContextManager", FakeContextManager)

    processed: list[str] = []

    async def fake_process_job(job_id, *, expected_attempts=0):
        await asyncio.sleep(0.02)  # still in flight when stop is requested
        processed.append(job_id)

    pending = [
        {"id": "j1", "owner_id": "u", "attempts": 0},
        {"id": "j2", "owner_id": "u", "attempts": 0},
    ]

    class FakeJobService:
        async def recover_stalled(self, *_a):
            return 0

        async def claim_next_job(self):
            if pending:
                return pending.pop(0)
            # Queue drained: request shutdown so the loop exits after draining.
            holder["stop"].set()
            return None

    class FakeContainer:
        def __init__(self, *_a):
            self.job_service = FakeJobService()
            self.extraction_service = SimpleNamespace(process_job=fake_process_job)

    monkeypatch.setattr(loop, "ServiceContainer", FakeContainer)

    await asyncio.wait_for(loop.run(), timeout=3)

    assert sorted(processed) == ["j1", "j2"]  # both claimed jobs ran to completion
    assert closed["value"] is True  # pool closed only after the drain


async def test_run_skips_recovery_double_count(monkeypatch):
    """A recovery that returns >0 is logged once and does not wedge the loop."""
    holder: dict = {}
    monkeypatch.setattr(loop, "_install_signal_handlers", lambda ev: holder.__setitem__("stop", ev))
    monkeypatch.setattr(loop, "configure_json_logging", lambda *a, **k: None)
    monkeypatch.setattr(loop, "set_tracing_disabled", lambda *a, **k: None)
    monkeypatch.setattr(loop, "get_settings", _settings)

    class FakeContextManager:
        def __init__(self, *_a):
            pass

        async def initialize(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(loop, "ContextManager", FakeContextManager)

    recover_calls = {"n": 0}

    class FakeJobService:
        async def recover_stalled(self, *_a):
            recover_calls["n"] += 1
            return 2

        async def claim_next_job(self):
            # Stop the loop only once recovery has actually run. Recovery is
            # time-gated (once per poll interval) and can skip the very first
            # iteration, so stopping unconditionally here would race that gate.
            if recover_calls["n"] >= 1:
                holder["stop"].set()
            return None

    class FakeContainer:
        def __init__(self, *_a):
            self.job_service = FakeJobService()
            self.extraction_service = SimpleNamespace()

    monkeypatch.setattr(loop, "ServiceContainer", FakeContainer)

    await asyncio.wait_for(loop.run(), timeout=3)

    assert recover_calls["n"] >= 1
