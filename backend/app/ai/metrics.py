"""Translate the Agents SDK ``Usage`` object into the job's token_usage shape.

The API contract requires at least ``input`` / ``output`` / ``total``; we also
keep ``cached_input`` and ``reasoning`` sub-counts when the provider reports them
(docs/schema.md says to store what the provider returns). Everything is read
defensively so a change in the SDK's Usage shape degrades to zeros rather than
crashing a job.
"""

from __future__ import annotations

from typing import Any


def usage_to_token_dict(usage: Any) -> dict[str, int]:
    """Build the token_usage dict from an SDK Usage (or anything Usage-like)."""
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens))

    tokens: dict[str, int] = {
        "input": input_tokens,
        "output": output_tokens,
        "total": total,
    }

    input_details = getattr(usage, "input_tokens_details", None)
    cached = getattr(input_details, "cached_tokens", 0) if input_details else 0
    if cached:
        tokens["cached_input"] = int(cached)

    output_details = getattr(usage, "output_tokens_details", None)
    reasoning = getattr(output_details, "reasoning_tokens", 0) if output_details else 0
    if reasoning:
        tokens["reasoning"] = int(reasoning)

    return tokens


def usage_from_exception(exc: BaseException) -> Any | None:
    """Recover token usage from a failed agent run, if the SDK attached it.

    When the Agents SDK aborts a run (max-turns exhausted, schema-validation
    failure), it attaches the consumed usage to the raised exception at
    ``exc.run_data.context_wrapper.usage``. Tokens were billed, so we surface them
    on the failed job rather than reporting null. Walks the ``__cause__`` chain
    (our retry wrapper re-raises ``from`` the original) and reads everything
    defensively so a shape change degrades to None, not a crash.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        run_data = getattr(current, "run_data", None)
        wrapper = getattr(run_data, "context_wrapper", None) if run_data else None
        usage = getattr(wrapper, "usage", None) if wrapper else None
        if usage is not None:
            return usage
        current = getattr(current, "__cause__", None)
    return None
