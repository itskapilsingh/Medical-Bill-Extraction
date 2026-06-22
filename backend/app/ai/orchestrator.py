from __future__ import annotations

import time

from pydantic import BaseModel, Field

from app.ai.agents.extraction.executor import ExtractionAgentExecutor
from app.ai.config import EXTRACTION_AGENT_CONFIG
from app.ai.context import RunContext
from app.ai.metrics import usage_to_token_dict
from app.ai.pricing import estimate_cost_usd
from app.models.extraction import ExtractionOutput


class OrchestratorResult(BaseModel):
    """Combined extraction output and per-run metrics for one document."""

    extraction: ExtractionOutput = Field(default_factory=ExtractionOutput)
    model: str = EXTRACTION_AGENT_CONFIG.model
    token_usage: dict = Field(default_factory=dict)
    cost_usd: float = 0.0
    agent_seconds: float = 0.0


class ExtractionOrchestrator:
    """Runs the extraction pipeline for one document.

    Today this is a single agent stage; the orchestrator owns the wiring so
    additional stages (e.g. a validation/critic pass) can be added here without
    touching the service or worker. Metrics are aggregated as the run completes.
    """

    async def run(self, ctx: RunContext) -> OrchestratorResult:
        t_start = time.perf_counter()

        output, usage = await ExtractionAgentExecutor().run(ctx)

        token_usage = usage_to_token_dict(usage)
        cost = estimate_cost_usd(
            EXTRACTION_AGENT_CONFIG.model,
            input_tokens=token_usage.get("input", 0),
            output_tokens=token_usage.get("output", 0),
            cached_input_tokens=token_usage.get("cached_input", 0),
        )

        return OrchestratorResult(
            extraction=output,
            model=EXTRACTION_AGENT_CONFIG.model,
            token_usage=token_usage,
            cost_usd=cost,
            agent_seconds=round(time.perf_counter() - t_start, 3),
        )
