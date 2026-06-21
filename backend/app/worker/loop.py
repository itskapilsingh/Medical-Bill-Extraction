import asyncio

from app.config.settings import get_settings
from app.core.common.logger import get_logger
from app.core.context_manager import ContextManager
from app.service.container import ServiceContainer

logger = get_logger(__name__)


async def run() -> None:
    """Main worker loop. Runs indefinitely, polling for pending jobs.

    On each iteration:
    1. Attempt to recover any stalled jobs from a previous crashed worker
    2. Claim the next pending job atomically
    3. If a job was claimed, run the extraction pipeline
    4. If the queue is empty, sleep and retry
    """
    settings = get_settings()
    context_manager = ContextManager(settings)
    await context_manager.initialize()
    container = ServiceContainer(context_manager)

    logger.info("worker_started", poll_interval=settings.WORKER_POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Recover jobs claimed by a crashed worker (no update for 5+ minutes)
            # await container.job_service.recover_stalled()

            # Claim and process the next pending job
            # job = await container.job_service.claim_next_job()
            # if job:
            #     logger.info("job_claimed", job_id=job["id"])
            #     await container.extraction_service.process_job(job["id"])
            # else:
            #     await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

            await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

        except Exception:
            logger.exception("worker_loop_error")
            await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)
