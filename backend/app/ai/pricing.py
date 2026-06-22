"""Token-usage cost estimation.

There are no hard cost targets this round, but the API must surface a ``cost_usd``
per job "based on documented pricing assumptions" (ASSIGNMENT.md). These are the
assumptions, in one place, easy to update.

Rates are USD per 1,000,000 tokens. Cached input tokens (when the provider
reports them) are billed at the cheaper cached rate and subtracted from the
billable input. If a model is unknown we fall back to the gpt-5.4-mini rates and
still return a number rather than failing the job over pricing.

NOTE: these figures are placeholders for this exercise — confirm against current
provider pricing before relying on them in production.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPriceTable:
    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float


# Assumed rates for the gpt-5.4 family (USD / 1M tokens).
_PRICES: dict[str, ModelPriceTable] = {
    "gpt-5.4": ModelPriceTable(1.25, 0.125, 10.0),
    "gpt-5.4-mini": ModelPriceTable(0.25, 0.025, 2.0),
    "gpt-5.4-nano": ModelPriceTable(0.05, 0.005, 0.40),
}

_DEFAULT = _PRICES["gpt-5.4-mini"]


def _resolve(model: str) -> ModelPriceTable:
    """Resolve a concrete model id to a price table (longest known prefix wins)."""
    if model in _PRICES:
        return _PRICES[model]
    candidates = [k for k in _PRICES if model.startswith(k)]
    if candidates:
        return _PRICES[max(candidates, key=len)]
    return _DEFAULT


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
