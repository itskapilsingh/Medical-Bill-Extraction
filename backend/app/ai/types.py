from pathlib import Path
from typing import List, Optional

from agents import Usage
from pydantic import BaseModel, Field


class Page(BaseModel):
    """A single page of a document."""

    page_num: int
    page_content: str
    on_disk__markdown_path: Optional[Path] = None
    on_disk__screenshot_path: Optional[Path] = None


class Document(BaseModel):
    doc_id: str
    num_pages: int
    pages: List[Page]


class RunMetrics(BaseModel):
    cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_cached_input_tokens: int = 0
    total_num_calls: int = 0

    usage_records: dict[str, list[Usage]] = Field(default_factory=dict)
