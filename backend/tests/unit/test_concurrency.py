import asyncio

import pytest

from app.ai.utils.concurrency import parallel_map, run_with_timeout

pytestmark = pytest.mark.asyncio


async def test_results_preserve_input_order():
    async def double(n: int) -> int:
        # Stagger completion so out-of-order finishing is possible.
        await asyncio.sleep(0.01 * (5 - n))
        return n * 2

    out = await parallel_map([1, 2, 3, 4], double, max_concurrent=4)
    assert out == [2, 4, 6, 8]


async def test_respects_concurrency_cap():
    active = 0
    peak = 0

    async def track(_: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return 0

    await parallel_map(range(10), track, max_concurrent=3)
    assert peak <= 3


async def test_exceptions_returned_as_elements():
    async def maybe_fail(n: int) -> int:
        if n == 2:
            raise ValueError("boom")
        return n

    out = await parallel_map([1, 2, 3], maybe_fail, return_exceptions=True)
    assert out[0] == 1 and out[2] == 3
    assert isinstance(out[1], ValueError)


async def test_propagates_when_not_returning_exceptions():
    async def maybe_fail(n: int) -> int:
        if n == 1:
            raise RuntimeError("nope")
        return n

    with pytest.raises(RuntimeError):
        await parallel_map([0, 1, 2], maybe_fail, return_exceptions=False)


async def test_per_item_timeout_surfaces_as_timeouterror():
    async def slow(_: int) -> int:
        await asyncio.sleep(1)
        return 1

    out = await parallel_map([0], slow, timeout=0.01, return_exceptions=True)
    assert isinstance(out[0], asyncio.TimeoutError)


async def test_run_with_timeout_none_means_no_limit():
    async def quick() -> str:
        return "ok"

    assert await run_with_timeout(quick(), None) == "ok"
