"""In-process sliding-window rate limiter.

This is the shared primitive behind both rate-limiting layers in the API:

* the per-IP :class:`~app.api.middleware.RateLimitMiddleware`, and
* the per-user upload guard (:mod:`app.api.dependencies.rate_limit`).

State lives in this process, so it is correct for the single API replica this
project deploys. Behind a load balancer with multiple replicas each replica would
grant the full budget independently — move the counters to a shared store (e.g.
Redis) or enforce limits at the ingress for that topology.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Per-key sliding window of recent request timestamps.

    :meth:`hit` records a request and reports whether the key is over budget.
    Idle keys are swept once per window so the state map cannot grow without
    bound (one deque per distinct key ever seen).
    """

    def __init__(self, *, window_seconds: float, max_requests: int) -> None:
        self._window = window_seconds
        self._max = max_requests
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = 0.0

    def _sweep(self, now: float) -> None:
        """Drop keys whose most recent hit predates the window (idle clients)."""
        cutoff = now - self._window
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] < cutoff]
        for k in stale:
            del self._hits[k]

    def hit(
        self,
        key: str,
        *,
        now: float | None = None,
        max_requests: int | None = None,
    ) -> int | None:
        """Record a request for ``key`` and report whether it is allowed.

        Returns ``None`` when the request is within budget (and counts it), or the
        integer ``Retry-After`` seconds when the budget is exhausted. A rejected
        request is **not** counted, so a caller that keeps hammering past the limit
        cannot keep pushing the window forward and starve itself indefinitely.

        ``max_requests`` overrides the limiter's default budget for this call,
        which lets one limiter serve several budgets keyed into the same map (the
        IP middleware uses this for its general vs. upload budgets).
        """
        if now is None:
            now = time.monotonic()
        limit = self._max if max_requests is None else max_requests

        # Bound the state map: sweep idle keys at most once per window.
        if now - self._last_sweep >= self._window:
            self._sweep(now)
            self._last_sweep = now

        hits = self._hits[key]
        cutoff = now - self._window
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(self._window - (now - hits[0])))
        hits.append(now)
        return None
