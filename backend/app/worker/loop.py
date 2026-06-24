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
                signal.signal(sig, lambda *_: stop_event.set())
            except (ValueError, OSError):
                pass  # not in the main thread / unsupported — best effort only


async def _interruptible_sleep(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, returning early if shutdown is requested."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def run() -> None:
    """Main worker loop. Polls for pending jobs until asked to stop.

    On each iteration:
    1. Recover any jobs stranded in `processing` by a crashed worker (time-gated).
    2. Claim the next pending job atomically (safe under N concurrent workers).
    3. If one was claimed, bind the job OWNER's database identity and process it
       — so the result write is RLS-scoped to the owner, exactly as if the owner
       had written it. The worker is never an isolation hole.
    4. If the queue is empty, sleep and retry.

    On SIGTERM/SIGINT it stops claiming new work, lets the in-flight job finish,
    and exits cleanly — so `docker compose down` doesn't strand a job mid-run.
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

    logger.info("worker_started", poll_interval=settings.WORKER_POLL_INTERVAL_SECONDS)

    sweep_interval = settings.RETENTION_SWEEP_INTERVAL_SECONDS
    last_sweep = monotonic() - sweep_interval  # sweep once on startup

    try:
        while not stop_event.is_set():
            try:
                if sweep_interval > 0 and monotonic() - last_sweep >= sweep_interval:
                    sweep_expired_pdfs(settings.PDF_MOUNT_PATH, settings.RETENTION_DAYS)
                    last_sweep = monotonic()

                recovered = await container.job_service.recover_stalled(
                    settings.WORKER_STALL_TIMEOUT_MINUTES,
                    settings.EXTRACTION_MAX_ATTEMPTS,
                )
                if recovered:
                    logger.warning("jobs_recovered", count=recovered)

                job = await container.job_service.claim_next_job()
                if job:
                    logger.info("job_claimed", job_id=job["id"], owner_id=job["owner_id"])
                    # The worker has no HTTP session; it writes as the job's owner.
                    # Pass the claimed attempts so a recovered/re-claimed job can't
                    # be clobbered by this run's terminal write. We let this finish
                    # even if a stop was requested mid-run — interrupting it would
                    # strand the job in `processing` for the recovery timer.
                    with acting_as(job["owner_id"]):
                        await container.extraction_service.process_job(
                            job["id"], expected_attempts=job["attempts"]
                        )
                else:
                    await _interruptible_sleep(
                        stop_event, settings.WORKER_POLL_INTERVAL_SECONDS
                    )
            except Exception:
                logger.exception("worker_loop_error")
                await _interruptible_sleep(
                    stop_event, settings.WORKER_POLL_INTERVAL_SECONDS
                )
    finally:
        logger.info("worker_stopping")
        await context_manager.close()
