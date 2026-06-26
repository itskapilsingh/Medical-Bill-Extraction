import asyncio
import signal
from time import monotonic

from agents import set_tracing_disabled

from app.config.settings import get_settings
from app.core.common.logger import configure_json_logging, get_logger
from app.core.context_manager import ContextManager
from app.core.identity import acting_as
from app.service.container import ServiceContainer
from app.worker.retention import sweep_expired_pdfs

logger = get_logger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Trip ``stop_event`` on SIGTERM/SIGINT so the loop can drain and exit.

    ``loop.add_signal_handler`` is the clean asyncio path but is unavailable on
    Windows; fall back to ``signal.signal`` there (the worker runs on Linux in
    Docker, where the async path is used — the fallback just keeps local dev sane).
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError, AttributeError, ValueError):
            try:
                # Schedule the set on the loop thread-safely so a signal arriving
                # while the loop is parked in wait_for() wakes it promptly.
                signal.signal(
                    sig, lambda *_: loop.call_soon_threadsafe(stop_event.set)
                )
            except (ValueError, OSError):
                pass  # not in the main thread / unsupported — best effort only


async def _interruptible_sleep(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, returning early if shutdown is requested."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _wait_for_capacity(
    in_flight: set[asyncio.Task], stop_event: asyncio.Event, timeout: float
) -> None:
    """Block until an in-flight job finishes (a slot frees), stop is requested, or
    ``timeout`` elapses — whichever comes first."""
    if not in_flight:
        await _interruptible_sleep(stop_event, timeout)
        return
    stop_task = asyncio.ensure_future(stop_event.wait())
    try:
        await asyncio.wait(
            {stop_task, *in_flight},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        stop_task.cancel()


async def _process_claimed(container: ServiceContainer, job: dict) -> None:
    """Run one claimed job under the OWNER's identity, so the result write is
    RLS-scoped to the owner exactly as if the owner had written it."""
    with acting_as(job["owner_id"]):
        await container.extraction_service.process_job(
            job["id"], expected_attempts=job["attempts"]
        )


async def run() -> None:
    """Main worker loop. Polls for pending jobs until asked to stop.

    Each replica processes up to ``WORKER_CONCURRENCY`` jobs at once: it keeps that
    many ``process_job`` coroutines in flight, claiming a new job (atomically, via
    FOR UPDATE SKIP LOCKED — safe across all replicas) whenever a slot is free.
    Extraction is I/O-bound on the model call, so this multiplies throughput
    without extra replicas. Periodically it recovers crash-stranded jobs and sweeps
    expired PDFs. On SIGTERM/SIGINT it stops claiming and drains in-flight jobs
    before exiting, so `docker compose down` never strands a job mid-run.
    """
    settings = get_settings()
    configure_json_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)

    # Keep API calls modest: don't export agent traces to OpenAI.
    set_tracing_disabled(True)

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    context_manager = ContextManager(settings)
    await context_manager.initialize()
    container = ServiceContainer(context_manager)

    concurrency = max(1, settings.WORKER_CONCURRENCY)
    poll = settings.WORKER_POLL_INTERVAL_SECONDS
    logger.info("worker_started", poll_interval=poll, concurrency=concurrency)

    in_flight: set[asyncio.Task] = set()
    sweep_interval = settings.RETENTION_SWEEP_INTERVAL_SECONDS
    last_sweep = monotonic() - sweep_interval  # sweep once on startup
    last_recover = monotonic() - poll  # recover once on startup

    try:
        while not stop_event.is_set():
            try:
                now = monotonic()
                if sweep_interval > 0 and now - last_sweep >= sweep_interval:
                    await asyncio.to_thread(
                        sweep_expired_pdfs,
                        settings.PDF_MOUNT_PATH,
                        settings.RETENTION_DAYS,
                    )
                    last_sweep = now
                if now - last_recover >= poll:
                    recovered = await container.job_service.recover_stalled(
                        settings.WORKER_STALL_TIMEOUT_MINUTES,
                        settings.EXTRACTION_MAX_ATTEMPTS,
                    )
                    if recovered:
                        logger.warning("jobs_recovered", count=recovered)
                    last_recover = now

                # Fill every free slot with freshly-claimed jobs.
                claimed_any = False
                while len(in_flight) < concurrency and not stop_event.is_set():
                    job = await container.job_service.claim_next_job()
                    if job is None:
                        break  # queue empty
                    claimed_any = True
                    logger.info("job_claimed", job_id=job["id"], owner_id=job["owner_id"])
                    task = asyncio.create_task(_process_claimed(container, job))
                    in_flight.add(task)
                    task.add_done_callback(in_flight.discard)

                if stop_event.is_set():
                    break
                if len(in_flight) >= concurrency:
                    await _wait_for_capacity(in_flight, stop_event, poll)
                elif not claimed_any:
                    await _interruptible_sleep(stop_event, poll)
                # else: claimed some with capacity left — loop again to claim more.
            except Exception:
                logger.exception("worker_loop_error")
                await _interruptible_sleep(stop_event, poll)
    finally:
        logger.info("worker_stopping", in_flight=len(in_flight))
        if in_flight:
            # Let the jobs we already claimed finish before we close the DB pool.
            await asyncio.gather(*in_flight, return_exceptions=True)
        await context_manager.close()
