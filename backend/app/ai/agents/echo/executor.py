from __future__ import annotations

from agents import Agent, Runner, Usage

from app.ai.agents.factory import AgentFactory
from app.ai.config import ECHO_AGENT_CONFIG
from app.ai.context import RunContext
from app.core.common.logger import get_logger


class EchoAgentExecutor:
    """Runs the echo agent over a document. Complete working example.

    Supplies page 1 text in the rendered user prompt and returns a one-sentence summary.
    Demonstrates the full executor pattern: prompt rendering, Runner.run(),
    and returning (output, usage).

    Use this as the template when adding new agent executors to the pipeline.
    """

    def __init__(
        self,
        *,
        agent: Agent[RunContext] | None = None,
        max_turns: int = 3,
    ) -> None:
        """Initialise the executor.

        Args:
            agent: Optional pre-built agent. Uses AgentFactory if not provided.
            max_turns: Maximum agent turns before forced stop.
        """
        self.agent = agent if agent is not None else AgentFactory.build_echo_agent()
        self.max_turns = max(1, max_turns)
        self.logger = get_logger(__name__)

    async def _render_user(self, ctx: RunContext) -> str:
        """Render the user prompt template for this document.

        Args:
            ctx: RunContext with loaded document and prompt_loader.

        Returns:
            Fully rendered user prompt string.
        """
        return await ctx.prompt_loader.render(
            ECHO_AGENT_CONFIG.input_key,
            {
                "doc_id": ctx.document.doc_id,
                "total_pages": ctx.document.num_pages,
                "page_1_content": next(
                    (p.page_content for p in ctx.document.pages if p.page_num == 1),
                    "(page 1 not found)",
                ),
            },
        )

    async def run(self, ctx: RunContext) -> tuple[str, Usage]:
        """Run the echo agent and return (output_text, usage).

        Args:
            ctx: RunContext with loaded document.

        Returns:
            Tuple of final output string and token usage for this stage.
        """
        user_text = await self._render_user(ctx)

        self.logger.info("echo_agent_started", doc_id=ctx.document.doc_id)

        result = await Runner.run(
            self.agent,
            user_text,
            context=ctx,
            max_turns=self.max_turns,
        )

        output = (
            result.final_output
            if isinstance(result.final_output, str)
            else str(result.final_output)
        )

        self.logger.info(
            "echo_agent_completed",
            doc_id=ctx.document.doc_id,
            chars=len(output),
        )

        return output, result.context_wrapper.usage
