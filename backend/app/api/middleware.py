"""HTTP middleware for the API: security headers (and rate limiting, added below).

The API returns JSON only and serves PHI, so the headers are restrictive:
``no-store`` (never cache PHI), a deny-all CSP/frame policy (defence-in-depth even
though it is not an HTML surface), nosniff, and HSTS for TLS deployments.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client fixed-window rate limiter (in-process).

    Two budgets: a stricter one for ``POST /jobs`` (uploads/extraction spend) and
    a general one for everything else. Keyed by client IP (honouring a single
    proxy hop via X-Forwarded-For). In-process state is fine for the single API
    replica here; a multi-replica deployment should move this to a shared store
    (Redis). ``/health`` is never limited.
    """

    def __init__(self, app, *, window_seconds, general_max, upload_max):
        super().__init__(app)
        self._window = window_seconds
        self._general_max = general_max
        self._upload_max = upload_max
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client(self, request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        is_upload = request.method == "POST" and request.url.path.rstrip("/") == "/jobs"
        limit = self._upload_max if is_upload else self._general_max
        bucket = "u:" if is_upload else "g:"
        key = bucket + self._client(request)

        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self._window
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, int(self._window - (now - hits[0])))
            return JSONResponse(
                status_code=429,
                content={"success": False, "message": "Rate limit exceeded"},
                headers={"Retry-After": str(retry), "Cache-Control": "no-store"},
            )
        hits.append(now)
        return await call_next(request)
