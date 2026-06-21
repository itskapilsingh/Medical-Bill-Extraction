from fastapi import APIRouter, Depends, UploadFile, File

from app.api.dependencies.container import get_container
from app.api.schema import SuccessResponse
from app.service.container import ServiceContainer

router = APIRouter()


@router.post("/")
async def create_job(
    file: UploadFile = File(...),
    container: ServiceContainer = Depends(get_container),
) -> SuccessResponse:
    """Upload a PDF and create a new extraction job.

    Saves the uploaded PDF to the configured mount volume and enqueues
    a job for the worker. Returns the created job including job_id and
    initial status.
    """
    raise NotImplementedError


@router.get("/")
async def list_jobs(
    status: str | None = None,
    container: ServiceContainer = Depends(get_container),
) -> SuccessResponse:
    """List all jobs, optionally filtered by status.

    Valid status values: pending, processing, completed, failed, cancelled.
    Returns jobs ordered by created_at descending.
    """
    raise NotImplementedError


@router.get("/active")
async def get_active_job(
    container: ServiceContainer = Depends(get_container),
) -> SuccessResponse:
    """Return the job currently being processed by the worker.

    Returns null if no job is currently processing.
    Must reflect live state on every call — do not cache.
    """
    raise NotImplementedError


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    container: ServiceContainer = Depends(get_container),
) -> SuccessResponse:
    """Return full detail for a single job.

    Includes extraction result if completed, error detail if failed.
    Returns 404 if the job does not exist.
    """
    raise NotImplementedError


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    container: ServiceContainer = Depends(get_container),
) -> SuccessResponse:
    """Cancel a pending job before it is picked up by the worker.

    Returns 409 if the job is already processing, completed, or failed.
    Returns 404 if the job does not exist.
    """
    raise NotImplementedError
