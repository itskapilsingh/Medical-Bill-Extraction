"""Request authentication: resolve the Better Auth session into an RLS identity.

Flow for every authenticated request:

1. Pull the session token from ``Authorization: Bearer <token>`` (how the Next.js
   BFF forwards it) or, as a fallback, the Better Auth session cookie (handy for
   hitting the API directly, e.g. Swagger or curl).
2. If the value is a *signed* cookie (``<raw>.<sig>``), verify the HMAC-SHA256
   signature with ``BETTER_AUTH_SECRET`` before trusting it. A bare token (no
   dot) is accepted as-is — the database lookup is the real authority.
3. Look the raw token up in the shared ``session`` table to resolve the user.
4. Bind that user id to the request context so ``ContextManager.session`` stamps
   it onto every transaction and RLS scopes every query.

The binding is undone on teardown, so nothing leaks into the next request that
reuses this worker/connection.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import unquote

from fastapi import Depends, Request

from app.config.settings import Settings, get_settings
from app.core.common.logger import get_logger
from app.core.identity import reset_current_user_id, set_current_user_id
from app.dao.pg.auth_dao import AuthDAO
from app.service.exceptions import UnauthorizedException

logger = get_logger(__name__)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# Better Auth uses the unprefixed name over HTTP and the __Secure- prefixed name
# over HTTPS; check both.
_COOKIE_NAMES = (
    "better-auth.session_token",
    "__Secure-better-auth.session_token",
)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str


def _extract_raw_token(request: Request, secret: str) -> str | None:
    """Return the raw (unsigned) session token from the request, or None."""
    auth_header = request.headers.get("authorization") or request.headers.get(
        "Authorization"
    )
    if auth_header and auth_header.lower().startswith("bearer "):
        return _unsign(auth_header[7:].strip(), secret)

    for name in _COOKIE_NAMES:
        cookie = request.cookies.get(name)
        if cookie:
            return _unsign(cookie, secret)
    return None


def _unsign(value: str, secret: str) -> str | None:
    """Strip and verify a Better Auth signed value.

    The cookie/bearer value is ``encodeURIComponent(rawToken + "." + base64(HMAC))``.
    A value with no ``.`` is treated as an already-raw token (the BFF forwards the
    raw ``session.token``); the DB lookup then decides validity. A signed value
    must pass constant-time HMAC verification or it is rejected outright.
    """
    decoded = unquote(value)
    if "." not in decoded:
        return decoded
    raw_token, signature = decoded.rsplit(".", 1)
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    if hmac.compare_digest(expected, signature):
        return raw_token
    return None


async def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[CurrentUser]:
    """FastAPI dependency yielding the authenticated user and binding RLS identity."""
    context_manager = request.app.state.context_manager
    raw_token = _extract_raw_token(request, settings.BETTER_AUTH_SECRET)
    if not raw_token:
        logger.warning(
            "auth_failed",
            reason="missing_or_malformed_token",
            path=request.url.path,
            client_ip=_client_ip(request),
        )
        raise UnauthorizedException("Missing or malformed session token")

    user = await AuthDAO(context_manager).get_session_user(raw_token)
    if user is None:
        logger.warning(
            "auth_failed",
            reason="invalid_or_expired_session",
            path=request.url.path,
            client_ip=_client_ip(request),
        )
        raise UnauthorizedException("Invalid or expired session")

    current = CurrentUser(id=user["id"], email=user["email"], name=user["name"])
    token = set_current_user_id(current.id)
    try:
        yield current
    finally:
        reset_current_user_id(token)
