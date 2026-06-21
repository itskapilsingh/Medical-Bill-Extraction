"""Async helpers: bounded parallel map and optional per-call timeouts."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def parallel_map(
    items: Sequence[T],
    fn: Callable[[T], Awaitable[R]],
    *,
    max_concurrent: int = 5,
    timeout: float | None = None,
    return_exceptions: bool = True,
    cancel_on_first_error: bool = False,
) -> list[R | BaseException]:
    """Run an async function over each item with a concurrency cap.

    Args:
        items: Inputs to process.
        fn: Async function taking one item and returning a result.
        max_concurrent: Maximum number of in-flight `fn` calls.
        timeout: If set, each awaitable is wrapped with `asyncio.wait_for`.
        return_exceptions: Passed to `asyncio.gather`; when True, exceptions
            become result elements instead of propagating.
        cancel_on_first_error: If an error escapes `gather` (when
            `return_exceptions` is False) or in outer handling, cancel tasks
            that are not done yet.

    Returns:
        List of per-item results, or `BaseException` instances when
        `return_exceptions` is True and a task failed.
    """
    semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def guarded(item: T) -> R:
        async with semaphore:
            return await run_with_timeout(fn(item), timeout)

    tasks = [asyncio.create_task(guarded(item)) for item in items]
    try:
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
    except BaseException:
        if cancel_on_first_error:
            for task in tasks:
                if not task.done():
                    task.cancel()
        raise


async def run_with_timeout(awaitable: Awaitable[R], timeout: float | None) -> R:
    """Await a coroutine, optionally with a timeout.

    Args:
        awaitable: The awaitable to run.
        timeout: Seconds to wait, or None for no limit.

    Returns:
        The awaitable's result.

    Raises:
        asyncio.TimeoutError: If `timeout` is exceeded.
    """
    if timeout is None:
        return await awaitable
    return await asyncio.wait_for(awaitable, timeout=timeout)
