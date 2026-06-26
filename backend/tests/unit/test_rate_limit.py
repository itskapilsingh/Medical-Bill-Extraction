"""RateLimitMiddleware: budgets, /health exemption, XFF spoof-resistance, sweep.

Driven by calling dispatch() directly with a fake request and a trivial
call_next, so the tests need no server, DB, or network.
"""

import json
from collections import deque
from types import SimpleNamespace

import pytest
from starlette.responses import Response

from app.api.middleware import RateLimitMiddleware, UploadBodyLimitMiddleware


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
async def test_429_uses_unified_envelope_and_headers():
    # The per-IP throttle returns the same envelope + Retry-After as the per-user
    # guard, so a client has one error shape to parse.
    mw = _mw(general=1)
    await mw.dispatch(_req(), _ok)             # spend the budget
    resp = await mw.dispatch(_req(), _ok)       # over budget -> 429
    assert resp.status_code == 429
    assert resp.headers["Cache-Control"] == "no-store"
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after >= 1
    body = json.loads(resp.body)
    assert body["success"] is False
    assert body["http_status"] == 429
    assert body["code"] == 4290
    assert body["error"]["retry_after_seconds"] == retry_after


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
    # Sweep mechanics now live on the shared SlidingWindowLimiter the middleware
    # delegates to; reach through mw._limiter to exercise them.
    mw = _mw(window=60)
    lim = mw._limiter
    lim._hits["g:idle"] = deque([0.0])         # far older than the window
    lim._hits["g:edge"] = deque([939.0])       # just past cutoff (940) -> dropped
    lim._hits["g:active"] = deque([970.0])     # live: inside window, < now -> kept
    lim._sweep(now=1000.0)                      # cutoff = 1000 - 60 = 940
    assert "g:idle" not in lim._hits
    assert "g:edge" not in lim._hits
    assert "g:active" in lim._hits            # would fail if cutoff were off by a window


@pytest.mark.asyncio
async def test_dispatch_gate_sweeps_idle_keys_across_window(monkeypatch):
    # Drive the REAL request path (dispatch), not _sweep() directly, so the
    # once-per-window gate that actually bounds the map is exercised.
    import app.api.middleware as mw_mod

    clock = {"t": 1000.0}
    monkeypatch.setattr(mw_mod.time, "monotonic", lambda: clock["t"])

    mw = _mw(general=5, window=60)
    await mw.dispatch(_req(peer="1.1.1.1"), _ok)
    assert "g:1.1.1.1" in mw._limiter._hits

    clock["t"] = 1000.0 + 61  # past the window -> next dispatch triggers the sweep
    await mw.dispatch(_req(peer="2.2.2.2"), _ok)
    assert "g:1.1.1.1" not in mw._limiter._hits  # idle key evicted via the dispatch gate
    assert "g:2.2.2.2" in mw._limiter._hits
    assert mw._limiter._last_sweep == 1061.0


@pytest.mark.asyncio
async def test_dispatch_gate_does_not_sweep_within_window(monkeypatch):
    import app.api.middleware as mw_mod

    clock = {"t": 1000.0}
    monkeypatch.setattr(mw_mod.time, "monotonic", lambda: clock["t"])

    mw = _mw(general=5, window=60)
    await mw.dispatch(_req(peer="1.1.1.1"), _ok)
    clock["t"] = 1000.0 + 30  # still inside the window -> no sweep
    await mw.dispatch(_req(peer="2.2.2.2"), _ok)
    assert "g:1.1.1.1" in mw._limiter._hits   # not swept; cadence gate held


@pytest.mark.asyncio
async def test_upload_body_limit_rejects_declared_oversize():
    async def downstream(scope, receive, send):
        await Response("ok")(scope, receive, send)

    mw = UploadBodyLimitMiddleware(app=downstream, max_bytes=5)
    sent = await _call_upload_middleware(mw, [b"ok"], declared=6)

    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_upload_body_limit_rejects_streamed_oversize_before_downstream():
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True
        await Response("ok")(scope, receive, send)

    mw = UploadBodyLimitMiddleware(app=downstream, max_bytes=5)
    sent = await _call_upload_middleware(mw, [b"abc", b"def"])

    assert sent[0]["status"] == 413
    assert called is False


@pytest.mark.asyncio
async def test_upload_body_limit_replays_allowed_body_to_downstream():
    seen = b""

    async def downstream(scope, receive, send):
        nonlocal seen
        while True:
            message = await receive()
            if message["type"] == "http.request":
                seen += message.get("body", b"")
                if not message.get("more_body", False):
                    break
        await Response("ok")(scope, receive, send)

    mw = UploadBodyLimitMiddleware(app=downstream, max_bytes=10)
    sent = await _call_upload_middleware(mw, [b"abc", b"def"])

    assert sent[0]["status"] == 200
    assert seen == b"abcdef"


async def _call_upload_middleware(mw, chunks, *, declared=None):
    headers = []
    if declared is not None:
        headers.append((b"content-length", str(declared).encode()))
    scope = {"type": "http", "method": "POST", "path": "/jobs", "headers": headers}
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    await mw(scope, receive, send)
    return sent
