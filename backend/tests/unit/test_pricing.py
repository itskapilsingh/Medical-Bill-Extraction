from app.ai.pricing import estimate_cost_usd


def test_mini_cost_math():
    # 1M input + 1M output at gpt-5.4-mini's assumed rates ($0.25 / $2.00).
    cost = estimate_cost_usd("gpt-5.4-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == round(0.25 + 2.0, 6)


def test_cached_input_is_cheaper():
    full = estimate_cost_usd("gpt-5.4-mini", input_tokens=1_000_000, output_tokens=0)
    cached = estimate_cost_usd(
        "gpt-5.4-mini", input_tokens=1_000_000, output_tokens=0, cached_input_tokens=1_000_000
    )
    assert cached < full
    assert cached == round(0.025, 6)  # all input billed at the cached rate


def test_unknown_model_falls_back_not_crashes():
    cost = estimate_cost_usd("some-future-model", input_tokens=1000, output_tokens=1000)
    assert cost > 0


def test_prefix_resolution():
    # A dated/suffixed id resolves to its family rate.
    assert estimate_cost_usd(
        "gpt-5.4-mini-2026-01-01", input_tokens=1_000_000, output_tokens=0
    ) == round(0.25, 6)


def test_zero_usage_is_zero_cost():
    assert estimate_cost_usd("gpt-5.4-mini", input_tokens=0, output_tokens=0) == 0.0
