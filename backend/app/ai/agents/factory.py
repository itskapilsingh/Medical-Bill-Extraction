from agents import Agent, RunContextWrapper

from app.ai.config import EXTRACTION_AGENT_CONFIG
from app.ai.context import RunContext
from app.ai.tools import list_pages, read_pages, search_document
from app.models.extraction import ExtractionOutput


class AgentFactory:
    """Builds `Agent[RunContext]` instances for pipeline stages.

    Each agent takes its instructions from a Jinja template via the
    ``prompt_loader`` on `RunContext`, its model config from `app.ai.config`, and
    its tools from `tools.py`.
    """

    @staticmethod
    def build_extraction_agent() -> Agent[RunContext]:
        """Extraction agent — navigates a billing PDF and emits ExtractionOutput.

        The structured ``output_type`` forces the model to finish by returning a
        validated ExtractionOutput (records + flagged) rather than free text, so
        the orchestration code never has to parse prose.
        """

        async def instructions(
            wrapper: RunContextWrapper[RunContext], agent: Agent
        ) -> str:
            return await wrapper.context.prompt_loader.render(
                EXTRACTION_AGENT_CONFIG.instructions_key, {}
            )

        return Agent[RunContext](
            name="extraction_agent",
            instructions=instructions,
            model=EXTRACTION_AGENT_CONFIG.model,
            model_settings=EXTRACTION_AGENT_CONFIG.model_settings,
            tools=[list_pages, read_pages, search_document],
            output_type=ExtractionOutput,
        )
