"""Classify extraction failures as transient (worth retrying) or fatal.

Transient = the call could succeed if tried again: rate limits, timeouts, dropped
connections, provider 5xx. Fatal = retrying won't help: a corrupt/missing PDF, a
validation error, a programming bug. We classify defensively by exception family,
class name, and HTTP status code so it keeps working across OpenAI SDK versions
without importing version-specific exception classes.
"""

from __future__ import annotations

import asyncio

# Class names raised by the OpenAI SDK for retryable conditions.
_TRANSIENT_NAMES = {
    "RateLimitError",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "APIError",
}


def is_transient(exc: BaseException) -> bool:
    """True if ``exc`` looks like a transient error worth retrying."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    if type(exc).__name__ in _TRANSIENT_NAMES:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    return False
