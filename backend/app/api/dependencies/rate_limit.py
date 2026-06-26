"""Per-authenticated-user request rate limiting for expensive routes.

The per-IP :class:`~app.api.middleware.RateLimitMiddleware` runs *before*
authentication, so it can only key on network origin. That is too coarse for the
upload route, where the real cost is paid LLM extraction per accepted job:

* many users may share one egress IP (corporate NAT) — a per-IP cap then punishes
  every tenant for one noisy neighbour and lets them starve each other, while
* one account may rotate IPs (mobile, proxies, cloud) to multiply its per-IP
  allowance and drive unbounded extraction spend.

This dependency runs *after* ``get_current_user``, so it keys the budget on the
authenticated user id. Each tenant gets an independent upload allowance regardless
of source IP, and no single account can run extraction without bound or crowd
others out of the worker pool. Rejected requests never reach job creation, so the
paid extraction is never triggered.

OWASP API4:2023 (Unrestricted Resource Consumption) / LLM10 (Unbounded
Consumption) / CWE-770.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.core.common.rate_limit import SlidingWindowLimiter
from app.service.exceptions import RateLimitExceededException

# Attribute on ``app.state`` holding the shared per-user upload limiter (created in
# the app lifespan). ``None`` when rate limiting is disabled via settings.
USER_UPLOAD_LIMITER_ATTR = "user_upload_limiter"


async def enforce_user_upload_rate_limit(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Reject the caller with 429 if they have exhausted their upload budget.

    A no-op when the limiter is absent (rate limiting disabled). Keyed on the
    authenticated user id, so the budget follows the account, not the connection.
    """
    limiter: SlidingWindowLimiter | None = getattr(
        request.app.state, USER_UPLOAD_LIMITER_ATTR, None
    )
    if limiter is None:
        return

    retry_after = limiter.hit(current_user.id)
    if retry_after is not None:
        raise RateLimitExceededException(retry_after)
