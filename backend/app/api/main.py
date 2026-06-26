from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies.rate_limit import USER_UPLOAD_LIMITER_ATTR
from app.api.middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    UploadBodyLimitMiddleware,
)
from app.api.routes import health, jobs
from app.config.settings import get_settings
from app.core.common.logger import configure_json_logging
from app.core.common.rate_limit import SlidingWindowLimiter
from app.core.context_manager import ContextManager
from app.service.container import ServiceContainer
from app.service.exceptions import BaseServiceException


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_json_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)

    context_manager = ContextManager(settings)
    await context_manager.initialize()

    app.state.context_manager = context_manager
    app.state.container = ServiceContainer(context_manager)
    # Per-user upload limiter (keyed on user id by the POST /jobs dependency).
    # A single shared instance so its window state spans every request.
    setattr(
        app.state,
        USER_UPLOAD_LIMITER_ATTR,
        SlidingWindowLimiter(
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            max_requests=settings.RATE_LIMIT_USER_UPLOAD_MAX_REQUESTS,
        )
        if settings.RATE_LIMIT_ENABLED
        else None,
    )

    yield

    await context_manager.close()


app = FastAPI(title="Medical Billing Extraction API", lifespan=lifespan)

_settings = get_settings()
# Outermost first: security headers wrap everything; rate limiting runs before routing.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(UploadBodyLimitMiddleware, max_bytes=_settings.MAX_UPLOAD_REQUEST_BYTES)
if _settings.RATE_LIMIT_ENABLED:
    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=_settings.RATE_LIMIT_WINDOW_SECONDS,
        general_max=_settings.RATE_LIMIT_MAX_REQUESTS,
        upload_max=_settings.RATE_LIMIT_UPLOAD_MAX_REQUESTS,
        trusted_proxies=_settings.trusted_proxy_set,
    )


@app.exception_handler(BaseServiceException)
async def service_exception_handler(request: Request, exc: BaseServiceException):
    return JSONResponse(
        status_code=exc.http_status.value,
        content=exc.to_dict(),
        headers=exc.headers or None,
    )


app.include_router(health.router, tags=["Health"])
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
