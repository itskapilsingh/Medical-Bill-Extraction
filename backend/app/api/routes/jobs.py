"""Job routes.

Every route here runs in the authenticated caller's context. The
``get_current_user`` dependency binds the user's RLS identity for the request, so
the service/DAO layers below need no explicit owner filtering — Postgres scopes
every row. Responses use the envelope documented in ``docs/schema.md``.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.api.dependencies.container import get_container
from app.api.dependencies.rate_limit import enforce_user_upload_rate_limit
from app.api.schema.job import JobResponse, JobsSummary
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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=JobResponse,
    dependencies=[Depends(enforce_user_upload_rate_limit)],
)
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

    Guarded by a per-user rate limit (``enforce_user_upload_rate_limit``): a burst
    over the per-window budget is rejected with 429 + ``Retry-After`` before any
    PDF is persisted or any paid extraction is queued.
    """
    data = await _read_capped(file, settings.MAX_UPLOAD_BYTES)
    storage = PdfStorage(settings.PDF_MOUNT_PATH)
    try:
        storage.validate(data)
        content_hash = storage.fingerprint(data)
    except InvalidPdfError as exc:
        raise InvalidUploadException(str(exc)) from exc

    if not bypass_cache:
        reusable = await container.job_service.create_reusable_job(
            owner_id=current_user.id,
            pdf_filename=file.filename or "upload.pdf",
            content_hash=content_hash,
        )
        if reusable is not None:
            return JobResponse.from_job(reusable)

    pdf_path: str | None = None
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
    if job["pdf_path"] != pdf_path:
        storage.delete(pdf_path)
    return JobResponse.from_job(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = Query(
        None,
        description="Filter by status: pending|processing|completed|failed|cancelled",
    ),
    limit: int = Query(
        100, ge=1, le=200, description="Max jobs to return (newest first)."
    ),
    offset: int = Query(0, ge=0, description="Number of jobs to skip (pagination)."),
    before_created_at: datetime | None = Query(
        None,
        description=(
            "Keyset cursor: the created_at of the last row already seen. Pass "
            "together with before_id to fetch strictly older rows. Preferred over "
            "offset — stable under concurrent inserts and avoids deep-offset scans."
        ),
    ),
    before_id: str | None = Query(
        None,
        description="Keyset cursor: the id of the last row seen. Must accompany before_created_at.",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> list[JobResponse]:
    """List the caller's jobs, newest first.

    Bounded by ``limit``. Paginate either with ``offset`` (simple) or, preferably,
    the ``before_created_at``/``before_id`` keyset cursor — the latter is immune to
    rows arriving at the head between pages and never pays a deep-OFFSET scan.
    """
    if (before_created_at is None) != (before_id is None):
        # 400 literal, not status.HTTP_400_BAD_REQUEST: the `status` query param
        # above shadows the imported fastapi.status module inside this function.
        raise HTTPException(
            status_code=400,
            detail="before_created_at and before_id must be provided together.",
        )
    before = (
        (before_created_at, before_id)
        if before_created_at is not None and before_id is not None
        else None
    )
    jobs = await container.job_service.list_jobs(
        status=status, limit=limit, offset=offset, before=before
    )
    return [JobResponse.from_job(j) for j in jobs]


@router.get("/active", response_model=list[JobResponse])
async def get_active_jobs(
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> list[JobResponse]:
    """Return the caller's currently-processing jobs (live state; never cached)."""
    jobs = await container.job_service.get_active_jobs()
    return [JobResponse.from_job(j) for j in jobs]


@router.get("/summary", response_model=JobsSummary)
async def get_jobs_summary(
    current_user: CurrentUser = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> JobsSummary:
    """Aggregate counts + financial totals across ALL the caller's jobs.

    Computed in SQL (RLS-scoped) so the dashboard's headline numbers are correct
    regardless of how many documents the user has — unlike summing a paged list.
    """
    return JobsSummary(**await container.job_service.get_summary())


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
