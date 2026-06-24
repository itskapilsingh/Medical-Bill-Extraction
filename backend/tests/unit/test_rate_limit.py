"""RateLimitMiddleware: budgets, /health exemption, XFF spoof-resistance, sweep.

Driven by calling dispatch() directly with a fake request and a trivial
call_next, so the tests need no server, DB, or network.
"""

from collections import deque
from types import SimpleNamespace

import pytest
from starlette.responses import Response

from app.api.middleware import RateLimitMiddleware


def _mw(*, general=3, upload=2, window=60, trusted=()):
    return RateLimitMiddleware(
        app=lambda scope, receive, send: None,
        window_seconds=window,
        general_max=general,
        upload_max=upload,
        trusted_proxies=trusted,
    )


def _req(path="/x", method="GET", peer="9.9.9.9", xff=None):
    headers = {} if xff is None else {"x-forwarded-for": xff}
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method=method,
        client=SimpleNamespace(host=peer),
        headers=headers,
    )


async def _ok(_request):
    return Response("ok")


async def _codes(mw, reqs):
    out = []
    for r in reqs:
        resp = await mw.dispatch(r, _ok)
        out.append(resp.status_code)
    return out


@pytest.mark.asyncio
async def test_general_budget_returns_429_after_limit():
    mw = _mw(general=3)
    assert await _codes(mw, [_req() for _ in range(5)]) == [200, 200, 200, 429, 429]


@pytest.mark.asyncio
async def test_upload_budget_is_stricter():
    mw = _mw(general=10, upload=2)
    reqs = [_req(path="/jobs", method="POST") for _ in range(4)]
    assert await _codes(mw, reqs) == [200, 200, 429, 429]


@pytest.mark.asyncio
async def test_health_is_exempt():
    mw = _mw(general=1)
    assert await _codes(mw, [_req(path="/health") for _ in range(5)]) == [200] * 5


@pytest.mark.asyncio
async def test_spoofed_xff_cannot_evade_when_peer_untrusted():
    # Rotating a forged X-Forwarded-For must NOT mint fresh buckets: with no
    # trusted proxy, every request keys on the real (unspoofable) peer.
    mw = _mw(general=3, trusted=())
    reqs = [_req(xff=f"1.2.3.{i}") for i in range(5)]
    assert await _codes(mw, reqs) == [200, 200, 200, 429, 429]


@pytest.mark.asyncio
async def test_trusted_proxy_xff_gets_per_client_budget():
    # When the peer IS the trusted proxy, distinct forwarded clients are distinct
    # buckets (so a real proxied deployment limits per end-user).
    mw = _mw(general=2, trusted={"9.9.9.9"})
    reqs = [
        _req(xff="1.1.1.1"), _req(xff="1.1.1.1"),  # client A -> 2 ok
        _req(xff="2.2.2.2"), _req(xff="2.2.2.2"),  # client B -> 2 ok
        _req(xff="1.1.1.1"),                         # client A 3rd -> 429
    ]
    assert await _codes(mw, reqs) == [200, 200, 200, 200, 429]


def test_sweep_drops_idle_keys_but_keeps_active():
    mw = _mw(window=60)
    mw._hits["g:idle"] = deque([0.0])        # last hit at t=0
    mw._hits["g:active"] = deque([1000.0])   # last hit at t=1000
    mw._sweep(now=1000.0)                     # cutoff = 940
    assert "g:idle" not in mw._hits
    assert "g:active" in mw._hits
