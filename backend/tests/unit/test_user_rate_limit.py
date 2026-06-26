"""Per-user upload rate-limit dependency (POST /jobs guard).

Calls ``enforce_user_upload_rate_limit`` directly with a fake request and a real
SlidingWindowLimiter — no server, DB, or auth needed. Verifies the contract the
route relies on: a burst over the per-user budget is rejected with 429 +
Retry-After, budgets are independent per user, and the guard is a no-op when the
limiter is disabled.
"""

from types import SimpleNamespace

import pytest

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.rate_limit import (
    USER_UPLOAD_LIMITER_ATTR,
    enforce_user_upload_rate_limit,
)
from app.core.common.rate_limit import SlidingWindowLimiter
from app.service.exceptions import RateLimitExceededException


def _request(limiter):
    state = SimpleNamespace()
    setattr(state, USER_UPLOAD_LIMITER_ATTR, limiter)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _user(user_id: str) -> CurrentUser:
    return CurrentUser(id=user_id, email=f"{user_id}@example.com", name=user_id)


async def _call(limiter, user):
    """Run the dependency once; return None on allow, the exception on 429."""
    try:
        await enforce_user_upload_rate_limit(_request(limiter), current_user=user)
        return None
    except RateLimitExceededException as exc:
        return exc


@pytest.mark.asyncio
async def test_burst_over_limit_returns_429_with_retry_after():
    limiter = SlidingWindowLimiter(window_seconds=60, max_requests=3)
    user = _user("alice")

    # First three uploads in the window are allowed.
    for _ in range(3):
        assert await _call(limiter, user) is None

    # The fourth is rejected with a 429 carrying a Retry-After header.
    exc = await _call(limiter, user)
    assert isinstance(exc, RateLimitExceededException)
    assert exc.http_status.value == 429
    assert exc.error_code == 4290
    retry_after = exc.headers["Retry-After"]
    assert int(retry_after) >= 1
    # Response envelope surfaces the same value for clients.
    assert exc.to_dict()["error"]["retry_after_seconds"] == int(retry_after)


@pytest.mark.asyncio
async def test_budget_is_per_user_not_global():
    limiter = SlidingWindowLimiter(window_seconds=60, max_requests=1)
    alice, bob = _user("alice"), _user("bob")

    assert await _call(limiter, alice) is None      # alice's only allowance
    assert await _call(limiter, bob) is None         # bob has his own budget
    assert isinstance(await _call(limiter, alice), RateLimitExceededException)
    # bob is unaffected by alice hitting her limit.
    assert isinstance(await _call(limiter, bob), RateLimitExceededException)


@pytest.mark.asyncio
async def test_disabled_limiter_is_a_noop():
    # When rate limiting is off the lifespan sets the limiter to None; the guard
    # must let every request through rather than erroring.
    user = _user("alice")
    for _ in range(50):
        assert await _call(None, user) is None
