"""Token-usage cost estimation.

There are no hard cost targets this round, but the API must surface a
``cost_usd`` per job "based on documented pricing assumptions" (ASSIGNMENT.md).
The assumptions live in Settings so operators can update them by environment
without changing code.

Rates are USD per 1,000,000 tokens. Cached input tokens (when the provider
reports them) are billed at the cheaper cached rate and subtracted from the
billable input. If a model is unknown we fall back to the configured
gpt-5.4-mini rates and still return a number rather than failing the job over
pricing. Update the ``LLM_PRICE_*`` env vars whenever provider pricing changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import get_settings


@dataclass(frozen=True)
class ModelPriceTable:
    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float


def _prices() -> dict[str, ModelPriceTable]:
    settings = get_settings()
    return {
        "gpt-5.4": ModelPriceTable(
            settings.LLM_PRICE_GPT_5_4_INPUT_PER_1M,
            settings.LLM_PRICE_GPT_5_4_CACHED_INPUT_PER_1M,
            settings.LLM_PRICE_GPT_5_4_OUTPUT_PER_1M,
        ),
        "gpt-5.4-mini": ModelPriceTable(
            settings.LLM_PRICE_GPT_5_4_MINI_INPUT_PER_1M,
            settings.LLM_PRICE_GPT_5_4_MINI_CACHED_INPUT_PER_1M,
            settings.LLM_PRICE_GPT_5_4_MINI_OUTPUT_PER_1M,
        ),
        "gpt-5.4-nano": ModelPriceTable(
            settings.LLM_PRICE_GPT_5_4_NANO_INPUT_PER_1M,
            settings.LLM_PRICE_GPT_5_4_NANO_CACHED_INPUT_PER_1M,
            settings.LLM_PRICE_GPT_5_4_NANO_OUTPUT_PER_1M,
        ),
    }


def _resolve(model: str) -> ModelPriceTable:
    """Resolve a concrete model id to a price table (longest known prefix wins)."""
    prices = _prices()
    if model in prices:
        return prices[model]
    candidates = [k for k in prices if model.startswith(k)]
    if candidates:
        return prices[max(candidates, key=len)]
    return prices["gpt-5.4-mini"]


def estimate_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    """Estimate spend for one job from token counts.

    Cached input is billed at the cheaper rate; the remaining (uncached) input at
    the full rate. Rounded to 6 decimals.
    """
    price = _resolve(model)
    uncached_input = max(0, input_tokens - cached_input_tokens)
    cost = (
        uncached_input * price.input_per_1m
        + cached_input_tokens * price.cached_input_per_1m
        + output_tokens * price.output_per_1m
    ) / 1_000_000
    return round(cost, 6)
