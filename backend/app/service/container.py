from app.core.context_manager import ContextManager
from app.service.job_service import JobService
from app.service.extraction_service import ExtractionService


class ServiceContainer:
    """Wires up and exposes application services.

    Created once at startup and stored on app.state.
    Services are lazily initialized on first access and cached for reuse.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        self._context_manager = context_manager
        self._job_service: JobService | None = None
        self._extraction_service: ExtractionService | None = None

    @property
    def job_service(self) -> JobService:
        if self._job_service is None:
            self._job_service = JobService(self._context_manager)
        return self._job_service

    @property
    def extraction_service(self) -> ExtractionService:
        if self._extraction_service is None:
            self._extraction_service = ExtractionService(self._context_manager)
        return self._extraction_service
