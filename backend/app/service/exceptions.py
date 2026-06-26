from http import HTTPStatus
from typing import Any


class BaseServiceException(Exception):
    """Base exception for all service layer errors.

    Converted to a JSON error response by the FastAPI exception handler.
    Never raise HTTPException from a service — raise a subclass of this instead.
    """

    def __init__(
        self,
        message: str,
        error_code: int,
        http_status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.http_status = http_status
        self.details = details or {}
        # Extra response headers (e.g. Retry-After on a 429). Applied by the
        # FastAPI exception handler.
        self.headers = headers or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": False,
            "message": self.message,
            "code": self.error_code,
            "http_status": self.http_status.value,
            "error": self.details,
        }


class UnauthorizedException(BaseServiceException):
    def __init__(self, reason: str = "Authentication required") -> None:
        super().__init__(
            message=reason,
            error_code=4010,
            http_status=HTTPStatus.UNAUTHORIZED,
            details={},
        )


class InvalidUploadException(BaseServiceException):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=reason,
            error_code=4000,
            http_status=HTTPStatus.BAD_REQUEST,
            details={"reason": reason},
        )


class PayloadTooLargeException(BaseServiceException):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            message=f"Upload exceeds the maximum allowed size of {max_bytes} bytes",
            error_code=4130,
            http_status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            details={"max_bytes": max_bytes},
        )


class RateLimitExceededException(BaseServiceException):
    """429 raised by the per-user upload rate limiter.

    Carries a ``Retry-After`` header (seconds) so a well-behaved client knows when
    its budget refills. Maps to OWASP API4:2023 (Unrestricted Resource
    Consumption) / LLM10 (Unbounded Consumption) / CWE-770.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            message="Rate limit exceeded. Please retry later.",
            error_code=4290,
            http_status=HTTPStatus.TOO_MANY_REQUESTS,
            details={"retry_after_seconds": retry_after_seconds},
            headers={"Retry-After": str(retry_after_seconds)},
        )


class JobNotFoundException(BaseServiceException):
    def __init__(self, job_id: str) -> None:
        super().__init__(
            message=f"Job not found: {job_id}",
            error_code=4001,
            http_status=HTTPStatus.NOT_FOUND,
            details={"job_id": job_id},
        )


class JobNotCancellableException(BaseServiceException):
    def __init__(self, job_id: str, current_status: str) -> None:
        super().__init__(
            message=f"Job {job_id} cannot be cancelled in status: {current_status}",
            error_code=4002,
            http_status=HTTPStatus.CONFLICT,
            details={"job_id": job_id, "current_status": current_status},
        )
