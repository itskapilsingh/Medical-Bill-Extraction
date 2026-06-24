"""Trusted-proxy-aware client IP resolution.

``X-Forwarded-For`` is set by clients and can be forged. We only believe it when
the immediate TCP peer (``request.client.host``) is a configured trusted proxy;
otherwise a client talking to the API directly could spoof the header to evade
per-IP rate limits or poison audit logs. With no trusted proxies configured — the
default for the directly-exposed single-container setup — we always key on the
real peer, which a direct attacker cannot forge.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.requests import Request


def client_ip(request: Request, trusted_proxies: Iterable[str] = ()) -> str:
    """Best-effort source IP for rate-limiting and audit logging.

    Returns the left-most ``X-Forwarded-For`` entry (the original client) only
    when the peer is a trusted proxy; otherwise the real TCP peer.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in set(trusted_proxies):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return peer
