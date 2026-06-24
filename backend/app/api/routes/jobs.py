"""Job routes.

Every route here runs in the authenticated caller's context. The
``get_current_user`` dependency binds the user's RLS identity for the request, so
the service/DAO layers below need no explicit owner filtering — Postgres scopes
every row. Responses use the envelope documented in ``docs/schema.md``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.api.dependencies.container import get_container
from app.api.schema.job import JobResponse
from app.config.settings import Settings, get_settings
from app.core.storage import InvalidPdfError, PdfStorage
from app.service.container import ServiceContainer
from app.service.exceptions import InvalidUploadException, PayloadTooLargeException

router = APIRouter()

_UPLOAD_CHUNK = 1024 * 1024  # 1 MiB


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks, aborting as soon as it exceeds ``max_bytes``.

    Avoids buffering an unbounded payload into memory: we never accumulate more
    than ``max_bytes`` (+ one chunk) before rejecting with 413.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeException(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=JobResponse)
async def create_job(
    file: UploadFile = File(...),
    bypass_cache: bool = Query(
        False,
        description="Skip per-user result caching and always run a fresh extraction.",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    """Upload a PDF and create an extraction job owned by the caller.

    The file is persisted to the shared volume and a ``pending`` job is created.
    ``bypass_cache`` is accepted now and honoured by the caching layer in M3.
    """
    data = await _read_capped(file, settings.MAX_UPLOAD_BYTES)
    storage = PdfStorage(settings.PDF_MOUNT_PATH)
    try:
        pdf_path, content_hash = storage.save(owner_id=current_user.id, data=data)
    except InvalidPdfError as exc:
        raise InvalidUploadException(str(exc)) from exc

    job = await container.job_service.create_job(
        owner_id=current_user.id,
        pdf_filename=file.filename or "upload.pdf",
        pdf_path=pdf_path,
        content_hash=content_hash,
        bypass_cache=bypass_cache,
    )
    return JobResponse.from_job(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = Query(
        None,
        description="Filter by status: pending|processing|completed|failed|cancelled",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> list[JobResponse]:
    """List the caller's jobs, newest first."""
    jobs = await container.job_service.list_jobs(status=status)
    return [JobResponse.from_job(j) for j in jobs]


@router.get("/active", response_model=list[JobResponse])
async def get_active_jobs(
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> list[JobResponse]:
    """Return the caller's currently-processing jobs (live state; never cached)."""
    jobs = await container.job_service.get_active_jobs()
    return [JobResponse.from_job(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> JobResponse:
    """Return full detail for a single job the caller owns.

    A job owned by another user is indistinguishable from one that does not
    exist: both yield 404 (RLS returns no row in either case).
    """
    job = await container.job_service.get_job(job_id)
    return JobResponse.from_job(job)


@router.delete("/{job_id}", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> JobResponse:
    """Cancel a pending job the caller owns.

    404 if not visible to the caller; 409 if it is already processing/completed/
    failed/cancelled.
    """
    job = await container.job_service.cancel_job(job_id)
    return JobResponse.from_job(job)
