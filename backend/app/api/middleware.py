"""HTTP middleware for the API: security headers (and rate limiting, added below).

The API returns JSON only and serves PHI, so the headers are restrictive:
``no-store`` (never cache PHI), a deny-all CSP/frame policy (defence-in-depth even
though it is not an HTML surface), nosniff, and HSTS for TLS deployments.
"""

from __future__ import annotations

import time
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.common.net import client_ip
from app.core.common.rate_limit import SlidingWindowLimiter
from app.service.exceptions import PayloadTooLargeException, RateLimitExceededException

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


class UploadBodyLimitMiddleware:
    """Reject upload requests before FastAPI parses multipart form data."""

    def __init__(self, app, *, max_bytes: int) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path", "").rstrip("/") != "/jobs"
        ):
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        declared = headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self._max_bytes:
                    await self._send_too_large(scope, receive, send)
                    return
            except ValueError:
                await self._send_too_large(scope, receive, send)
                return

        total = 0
        messages = []
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            total += len(message.get("body", b""))
            if total > self._max_bytes:
                await self._send_too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _send_too_large(self, scope, receive, send) -> None:
        exc = PayloadTooLargeException(self._max_bytes)
        response = JSONResponse(
            status_code=exc.http_status.value,
            content=exc.to_dict(),
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client fixed-window rate limiter (in-process).

    Two budgets: a stricter one for ``POST /jobs`` (uploads/extraction spend) and
    a general one for everything else. Keyed by client IP — and the IP is resolved
    via :func:`client_ip`, so ``X-Forwarded-For`` is trusted only from a configured
    proxy; a direct client cannot spoof the header to land in a fresh bucket. The
    underlying :class:`SlidingWindowLimiter` sweeps idle keys once per window so
    state cannot accumulate without bound. ``/health`` is exempt.

    This stops bursts by network origin and runs before authentication. The
    finer-grained, per-authenticated-user budget for the expensive upload route
    lives in :mod:`app.api.dependencies.rate_limit` (it needs the resolved user
    id, which is only available after auth).

    In-process state is fine for the single API replica here; a multi-replica
    deployment should move this to a shared store (Redis).
    """

    def __init__(
        self,
        app,
        *,
        window_seconds,
        general_max,
        upload_max,
        trusted_proxies: Iterable[str] = (),
    ):
        super().__init__(app)
        self._upload_max = upload_max
        self._trusted = frozenset(trusted_proxies)
        # One limiter serves both budgets: bucket-prefixed keys keep the general
        # and upload counts separate, and ``hit`` takes a per-call budget override.
        self._limiter = SlidingWindowLimiter(
            window_seconds=window_seconds, max_requests=general_max
        )

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        is_upload = request.method == "POST" and request.url.path.rstrip("/") == "/jobs"
        bucket = "u:" if is_upload else "g:"
        key = bucket + client_ip(request, self._trusted)
        limit = self._upload_max if is_upload else None  # None -> limiter default

        retry = self._limiter.hit(key, now=time.monotonic(), max_requests=limit)
        if retry is not None:
            exc = RateLimitExceededException(retry)
            return JSONResponse(
                status_code=exc.http_status.value,
                content=exc.to_dict(),
                headers={**exc.headers, "Cache-Control": "no-store"},
            )
        return await call_next(request)
