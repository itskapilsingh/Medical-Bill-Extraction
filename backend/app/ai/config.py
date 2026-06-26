from agents.model_settings import ModelSettings, Reasoning
from pydantic import BaseModel

from app.config.settings import get_settings

ALLOWED_EXTRACTION_MODELS = frozenset({"gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"})


class AgentConfig(BaseModel):
    """Configuration for a single agent stage.

    instructions_key and input_key are paths relative to ``app/ai/prompts/templates/``
    (the default root used by ``PromptLoader``).
    """

    model: str
    model_settings: ModelSettings
    instructions_key: str
    input_key: str


def validate_extraction_model(model: str) -> str:
    """Enforce the assignment's OpenAI model policy for extraction paths."""
    if "-pro" in model:
        raise ValueError(f"Extraction model must not use a pro variant: {model}")
    if model not in ALLOWED_EXTRACTION_MODELS:
        allowed = ", ".join(sorted(ALLOWED_EXTRACTION_MODELS))
        raise ValueError(f"Unsupported extraction model {model!r}; allowed: {allowed}")
    return model


settings = get_settings()


EXTRACTION_AGENT_CONFIG = AgentConfig(
    model=validate_extraction_model(settings.EXTRACTION_MODEL),
    model_settings=ModelSettings(
        reasoning=Reasoning(effort="low"),
        verbosity="low",
    ),
    instructions_key="extraction/system.j2",
    input_key="extraction/user.j2",
)

PDF_FILE_EXTRACTION_CONFIG = AgentConfig(
    model=validate_extraction_model(settings.PDF_FILE_EXTRACTION_MODEL),
    model_settings=ModelSettings(
        reasoning=Reasoning(effort="low"),
        verbosity="low",
    ),
    instructions_key="extraction/pdf_file_system.j2",
    input_key="extraction/pdf_file_user.j2",
)
