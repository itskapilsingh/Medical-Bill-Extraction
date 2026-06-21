from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.prompts.prompt_loader import PromptLoader
from app.ai.types import Document


def new_session_id(doc_id: str) -> str:
    """Build a unique session ID for one document run."""
    return f"{doc_id}-{datetime.now().isoformat()}"


class RunContext(BaseModel):
    """Shared context passed into every agent executor for a single document run.

    All agents in a pipeline share the same RunContext instance. Executors may
    attach their outputs as new fields so downstream stages can consume them.
    Add fields here as your pipeline grows — do not pass outputs as function
    arguments between executors.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    document: Document
    prompt_loader: PromptLoader = Field(default_factory=PromptLoader)
    session_id: str | None = None

    @model_validator(mode="after")
    def default_session_id(self) -> Self:
        if self.session_id is None:
            self.session_id = new_session_id(self.document.doc_id)
        return self
