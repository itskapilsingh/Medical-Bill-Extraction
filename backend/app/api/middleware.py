"""HTTP middleware for the API: security headers (and rate limiting, added below).

The API returns JSON only and serves PHI, so the headers are restrictive:
``no-store`` (never cache PHI), a deny-all CSP/frame policy (defence-in-depth even
though it is not an HTML surface), nosniff, and HSTS for TLS deployments.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.common.net import client_ip

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
    a general one for everything else. Keyed by client IP — and the IP is resolved
    via :func:`client_ip`, so ``X-Forwarded-For`` is trusted only from a configured
    proxy; a direct client cannot spoof the header to land in a fresh bucket. The
    state map is swept once per window so idle keys cannot accumulate without bound.
    In-process state is fine for the single API replica here; a multi-replica
    deployment should move this to a shared store (Redis). ``/health`` is exempt.
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
        self._window = window_seconds
        self._general_max = general_max
        self._upload_max = upload_max
        self._trusted = frozenset(trusted_proxies)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = 0.0

    def _sweep(self, now: float) -> None:
        """Drop keys whose most recent hit is older than the window (idle clients).

        Bounds the state map to clients seen within roughly the last window, so a
        long-lived process can't leak one deque per distinct IP it has ever seen.
        """
        cutoff = now - self._window
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] < cutoff]
        for k in stale:
            del self._hits[k]

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        now = time.monotonic()
        if now - self._last_sweep >= self._window:
            self._sweep(now)
            self._last_sweep = now

        is_upload = request.method == "POST" and request.url.path.rstrip("/") == "/jobs"
        limit = self._upload_max if is_upload else self._general_max
        bucket = "u:" if is_upload else "g:"
        key = bucket + client_ip(request, self._trusted)

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
