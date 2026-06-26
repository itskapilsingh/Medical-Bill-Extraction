"""SlidingWindowLimiter: the shared in-process primitive.

Pure logic — the clock is injected via ``now`` so no real time passes. Both the
per-IP middleware and the per-user upload guard delegate to this class, so its
contract is exercised here once rather than through each caller.
"""

from collections import deque

from app.core.common.rate_limit import SlidingWindowLimiter


def test_allows_up_to_limit_then_blocks():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=3)
    assert lim.hit("u1", now=0.0) is None
    assert lim.hit("u1", now=1.0) is None
    assert lim.hit("u1", now=2.0) is None
    # 4th within the window is rejected with a positive Retry-After.
    retry = lim.hit("u1", now=3.0)
    assert isinstance(retry, int) and retry >= 1


def test_retry_after_counts_down_to_window_edge():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=1)
    assert lim.hit("u1", now=0.0) is None
    # Oldest hit was at t=0; at t=10 the window frees up in 50s.
    assert lim.hit("u1", now=10.0) == 50


def test_blocked_request_is_not_counted():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=1)
    assert lim.hit("u1", now=0.0) is None
    assert lim.hit("u1", now=5.0) is not None     # blocked
    assert lim.hit("u1", now=10.0) is not None    # still blocked
    assert lim.hit("u1", now=61.0) is None


def test_window_slides_and_frees_budget():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=2)
    assert lim.hit("u1", now=0.0) is None
    assert lim.hit("u1", now=1.0) is None
    assert lim.hit("u1", now=2.0) is not None     # over budget inside the window
    assert lim.hit("u1", now=61.0) is None


def test_keys_are_isolated():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=1)
    assert lim.hit("u1", now=0.0) is None
    assert lim.hit("u2", now=0.0) is None         # different key, own budget
    assert lim.hit("u1", now=1.0) is not None     # u1 exhausted


def test_max_requests_override_per_call():
    # The IP middleware uses one limiter for two budgets via this override.
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=10)
    assert lim.hit("u:1.1.1.1", now=0.0, max_requests=2) is None
    assert lim.hit("u:1.1.1.1", now=1.0, max_requests=2) is None
    assert lim.hit("u:1.1.1.1", now=2.0, max_requests=2) is not None


def test_sweep_bounds_the_state_map():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=5)
    lim._hits["idle"] = deque([0.0])              # last hit far before the window
    lim._hits["active"] = deque([970.0])
    lim._sweep(now=1000.0)                         # cutoff = 940
    assert "idle" not in lim._hits
    assert "active" in lim._hits


def test_dispatch_gate_sweeps_idle_keys_once_per_window():
    lim = SlidingWindowLimiter(window_seconds=60, max_requests=5)
    assert lim.hit("u1", now=1000.0) is None
    assert "u1" in lim._hits
    # Next hit is past the window -> gate fires, idle "u1" is swept.
    assert lim.hit("u2", now=1061.0) is None
    assert "u1" not in lim._hits
    assert "u2" in lim._hits
