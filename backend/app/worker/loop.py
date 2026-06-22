import asyncio

from agents import set_tracing_disabled

from app.config.settings import get_settings
from app.core.common.logger import configure_json_logging, get_logger
from app.core.context_manager import ContextManager
from app.core.identity import acting_as
from app.service.container import ServiceContainer

logger = get_logger(__name__)


async def run() -> None:
    """Main worker loop. Runs indefinitely, polling for pending jobs.

    On each iteration:
    1. Claim the next pending job atomically (safe under N concurrent workers).
    2. If one was claimed, bind the job OWNER's database identity and process it
       — so the result write is RLS-scoped to the owner, exactly as if the owner
       had written it. The worker is never an isolation hole.
    3. If the queue is empty, sleep and retry.

    Crash recovery for jobs stuck in `processing` is M3 (JobDAO.recover_stalled).
    """
    settings = get_settings()
    configure_json_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)

    # Keep API calls modest: don't export agent traces to OpenAI.
    set_tracing_disabled(True)

    context_manager = ContextManager(settings)
    await context_manager.initialize()
    container = ServiceContainer(context_manager)

    logger.info("worker_started", poll_interval=settings.WORKER_POLL_INTERVAL_SECONDS)

    try:
        while True:
            try:
                job = await container.job_service.claim_next_job()
                if job:
                    logger.info("job_claimed", job_id=job["id"], owner_id=job["owner_id"])
                    # The worker has no HTTP session; it writes as the job's owner.
                    with acting_as(job["owner_id"]):
                        await container.extraction_service.process_job(job["id"])
                else:
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
            except Exception:
                logger.exception("worker_loop_error")
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
    finally:
        await context_manager.close()
