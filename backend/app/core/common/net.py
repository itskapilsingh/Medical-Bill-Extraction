"""Trusted-proxy-aware client IP resolution.

``X-Forwarded-For`` is set by clients and can be forged. We only believe it when
the immediate TCP peer (``request.client.host``) is a configured trusted proxy;
otherwise a client talking to the API directly could spoof the header to evade
per-IP rate limits or poison audit logs. With no trusted proxies configured — the
default for the directly-exposed single-container setup — we always key on the
real peer, which a direct attacker cannot forge.

When a proxy IS trusted, we read the chain from the RIGHT: a reverse proxy
*appends* the address it saw to whatever ``X-Forwarded-For`` the client already
sent, so the trustworthy value is the right-most entry contributed by our own
proxy hops — never the left-most, which is client-supplied and forgeable.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.requests import Request


def client_ip(request: Request, trusted_proxies: Iterable[str] = ()) -> str:
    """Best-effort source IP for rate-limiting and audit logging.

    If the peer is a trusted proxy, walk ``X-Forwarded-For`` right-to-left,
    skipping entries that are themselves trusted proxies, and return the first
    non-trusted address (the real client as seen by our innermost proxy). Anything
    further left is client-supplied and ignored. Otherwise — or if every entry is
    a trusted proxy — return the real TCP peer.
    """
    peer = request.client.host if request.client else "unknown"
    trusted = set(trusted_proxies)
    if peer in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            hops = [p.strip() for p in forwarded.split(",") if p.strip()]
            for hop in reversed(hops):
                if hop not in trusted:
                    return hop
    return peer
