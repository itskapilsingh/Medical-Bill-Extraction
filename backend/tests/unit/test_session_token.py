"""The API's session-token verifier must agree, byte for byte, with how Better
Auth signs the cookie: ``encodeURIComponent(raw + "." + base64(HMAC_SHA256(raw,
secret)))`` using *standard* base64. These tests pin that contract."""

import base64
import hashlib
import hmac
from urllib.parse import quote

from app.api.dependencies.auth import _unsign

SECRET = "a-test-better-auth-secret"


def better_auth_cookie(raw: str, secret: str) -> str:
    """Reproduce Better Auth's signCookieValue for a raw token."""
    sig = base64.b64encode(
        hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    return quote(f"{raw}.{sig}")  # encodeURIComponent


def test_valid_signed_cookie_yields_raw_token():
    raw = "Hh3kZ9_rawSessionToken-abc"
    assert _unsign(better_auth_cookie(raw, SECRET), SECRET) == raw


def test_tampered_signature_is_rejected():
    raw = "Hh3kZ9_rawSessionToken-abc"
    forged = quote(f"{raw}.{base64.b64encode(b'not-the-real-sig').decode()}")
    assert _unsign(forged, SECRET) is None


def test_wrong_secret_is_rejected():
    raw = "Hh3kZ9_rawSessionToken-abc"
    assert _unsign(better_auth_cookie(raw, "different-secret"), SECRET) is None


def test_bare_token_passes_through():
    # The BFF forwards the raw session.token (no signature). The DB lookup is the
    # authority for these, so _unsign returns it unchanged.
    assert _unsign("rawTokenNoDot", SECRET) == "rawTokenNoDot"


def test_signature_with_base64_specials_round_trips():
    # Force a signature containing +,/,= so we exercise the URL-decoding path.
    for raw in ("a", "token+slash/equals=", "x" * 40):
        cookie = better_auth_cookie(raw, SECRET)
        assert _unsign(cookie, SECRET) == raw
