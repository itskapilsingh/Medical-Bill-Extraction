from __future__ import annotations

from agents import Runner, Usage

from app.ai.agents.factory import AgentFactory
from app.ai.config import EXTRACTION_AGENT_CONFIG
from app.ai.context import RunContext
from app.config.settings import get_settings
from app.core.common.logger import get_logger
from app.models.extraction import ExtractionOutput


class ExtractionAgentExecutor:
    """Runs the extraction agent over one document.

    The agent navigates the document with tools and returns a validated
    ExtractionOutput. ``max_turns`` bounds the tool-calling loop; large documents
    may need several read_pages calls, so it defaults (via settings) to a
    generous-but-finite budget.
    """

    def __init__(self, *, agent=None, max_turns: int | None = None) -> None:
        self.agent = agent if agent is not None else AgentFactory.build_extraction_agent()
        resolved = max_turns if max_turns is not None else get_settings().EXTRACTION_MAX_TURNS
        self.max_turns = max(1, resolved)
        self.logger = get_logger(__name__)

    async def _render_user(self, ctx: RunContext) -> str:
        return await ctx.prompt_loader.render(
            EXTRACTION_AGENT_CONFIG.input_key,
            {"doc_id": ctx.document.doc_id, "total_pages": ctx.document.num_pages},
        )

    async def run(self, ctx: RunContext) -> tuple[ExtractionOutput, Usage]:
        """Run the agent and return (ExtractionOutput, token usage)."""
        user_text = await self._render_user(ctx)
        self.logger.info(
            "extraction_agent_started",
            doc_id=ctx.document.doc_id,
            pages=ctx.document.num_pages,
        )

        result = await Runner.run(
            self.agent,
            user_text,
            context=ctx,
            max_turns=self.max_turns,
        )

        output = result.final_output
        if not isinstance(output, ExtractionOutput):
            # output_type guarantees this, but stay defensive rather than persist junk.
            output = ExtractionOutput()

        self.logger.info(
            "extraction_agent_completed",
            doc_id=ctx.document.doc_id,
            records=len(output.records),
            flagged=len(output.flagged),
        )
        return output, result.context_wrapper.usage
