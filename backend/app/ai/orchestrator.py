from __future__ import annotations

import time

from pydantic import BaseModel, Field

from app.ai.agents.echo.executor import EchoAgentExecutor
from app.ai.context import RunContext
from app.ai.types import RunMetrics


class OrchestratorResult(BaseModel):
    """Combined outputs and metrics for one document run."""

    echo_result: str | None = None
    billing_records: list[dict] = Field(default_factory=list)
    run_metrics: dict[str, RunMetrics] = Field(default_factory=dict)
    wall_clock_seconds: float = 0.0


class ExtractionOrchestrator:
    """Runs the extraction pipeline for one document.

    Wire additional executors here as you extend the pipeline; attach outputs on
    `RunContext` when later stages need them, and aggregate metrics as you go.
    """

    async def run(self, ctx: RunContext) -> OrchestratorResult:
        """Run pipeline stages and return combined result."""
        t_start = time.perf_counter()
        metrics: dict[str, RunMetrics] = {}

        echo_output, echo_usage = await EchoAgentExecutor().run(ctx)
        # NOTE: echo_usage is a raw SDK Usage object. RunMetrics is our
        # aggregated model. Decide how to bridge these as you build out
        # the pipeline — see app/ai/types.py for RunMetrics definition.

        return OrchestratorResult(
            echo_result=echo_output,
            billing_records=[],
            run_metrics=metrics,
            wall_clock_seconds=time.perf_counter() - t_start,
        )
