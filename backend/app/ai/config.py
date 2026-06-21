from agents.model_settings import ModelSettings, Reasoning
from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Configuration for a single agent stage.

    instructions_key and input_key are paths relative to ``app/ai/prompts/templates/``
    (the default root used by ``PromptLoader``).
    """

    model: str
    model_settings: ModelSettings
    instructions_key: str
    input_key: str


# Working example — pair with AgentFactory.build_* and matching Jinja templates.
ECHO_AGENT_CONFIG = AgentConfig(
    model="gpt-5.4-nano",
    model_settings=ModelSettings(
        reasoning=Reasoning(effort="none"),
        verbosity="low",
    ),
    instructions_key="echo/system.j2",
    input_key="echo/user.j2",
)

# Add further AgentConfig constants here for additional agents.
