"""Request/job-scoped database identity.

The authenticated user id is carried out-of-band in a :class:`contextvars.ContextVar`
rather than threaded through every service and DAO call. ``ContextManager.session``
reads it and issues ``set_config('app.user_id', <id>, is_local => true)`` at the start
of each transaction, so Postgres Row-Level Security policies can filter on
``current_setting('app.user_id')``.

Why a contextvar instead of an argument:

- DAOs already open their own sessions through ``ContextManager.session``; passing an
  id through every method would be invasive and easy to forget — and a forgotten id is
  exactly the leak RLS exists to prevent.
- ``contextvars`` are coroutine/task-local, so concurrent requests (and the worker's
  per-job runs) never see each other's identity.

The setting is applied with ``is_local => true``, so it lives only for the duration of
the transaction and is reset on COMMIT/ROLLBACK. That is what makes identity propagation
safe under connection pooling: a pooled connection handed to the next request never
carries the previous request's user id.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# None means "no authenticated identity". With no identity set, the RLS GUC is never
# applied, current_setting('app.user_id', true) is NULL, and every user-owned policy
# denies — a safe default-deny rather than an accidental open door.
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def get_current_user_id() -> str | None:
    """Return the user id bound to the current context, or None."""
    return _current_user_id.get()


def set_current_user_id(user_id: str | None) -> object:
    """Bind a user id to the current context. Returns a reset token."""
    return _current_user_id.set(user_id)


def reset_current_user_id(token: object) -> None:
    """Undo a previous :func:`set_current_user_id`."""
    _current_user_id.reset(token)  # type: ignore[arg-type]


@contextmanager
def acting_as(user_id: str | None) -> Iterator[None]:
    """Run a block under a specific database identity.

    Used by the worker, which has no HTTP request: after claiming a job it does
    ``with acting_as(job["owner_id"]):`` so the result it writes is subject to the
    same RLS policies as the owner's own requests.
    """
    token = set_current_user_id(user_id)
    try:
        yield
    finally:
        reset_current_user_id(token)
