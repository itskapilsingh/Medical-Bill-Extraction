from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.api.routes import health, jobs
from app.config.settings import get_settings
from app.core.common.logger import configure_json_logging
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

    yield

    await context_manager.close()


app = FastAPI(title="Medical Billing Extraction API", lifespan=lifespan)

_settings = get_settings()
# Outermost first: security headers wrap everything; rate limiting runs before routing.
app.add_middleware(SecurityHeadersMiddleware)
if _settings.RATE_LIMIT_ENABLED:
    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=_settings.RATE_LIMIT_WINDOW_SECONDS,
        general_max=_settings.RATE_LIMIT_MAX_REQUESTS,
        upload_max=_settings.RATE_LIMIT_UPLOAD_MAX_REQUESTS,
    )


@app.exception_handler(BaseServiceException)
async def service_exception_handler(request: Request, exc: BaseServiceException):
    return JSONResponse(
        status_code=exc.http_status.value,
        content=exc.to_dict(),
    )


app.include_router(health.router, tags=["Health"])
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
