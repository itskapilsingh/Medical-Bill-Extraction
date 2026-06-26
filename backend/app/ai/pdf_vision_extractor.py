from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.ai.config import PDF_FILE_EXTRACTION_CONFIG, validate_extraction_model
from app.ai.metrics import usage_to_token_dict
from app.ai.orchestrator import OrchestratorResult
from app.ai.pricing import estimate_cost_usd
from app.ai.prompts.prompt_loader import PromptLoader
from app.core.common.logger import get_logger
from app.models.extraction import ExtractionOutput

logger = get_logger(__name__)


class PdfVisionExtractor:
    """Extract billing records from the original PDF through OpenAI file input.

    Used only when the deterministic pdfplumber text path detects scanned or
    image-heavy pages that would make text-only extraction incomplete.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        prompt_loader: PromptLoader | None = None,
        model: str | None = None,
    ) -> None:
        self.client = client if client is not None else AsyncOpenAI()
        self.prompt_loader = prompt_loader if prompt_loader is not None else PromptLoader()
        self.model = validate_extraction_model(
            model if model is not None else PDF_FILE_EXTRACTION_CONFIG.model
        )

    async def run(self, *, pdf_path: str, job_id: str) -> OrchestratorResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        t_start = time.perf_counter()
        instructions = await self.prompt_loader.render(
            PDF_FILE_EXTRACTION_CONFIG.instructions_key, {}
        )
        user_text = await self.prompt_loader.render(
            PDF_FILE_EXTRACTION_CONFIG.input_key,
            {"doc_id": job_id, "filename": path.name},
        )

        uploaded_id: str | None = None
        try:
            with path.open("rb") as pdf_file:
                uploaded = await self.client.files.create(
                    file=pdf_file,
                    purpose="user_data",
                )
            uploaded_id = uploaded.id
            logger.info(
                "pdf_vision_extraction_started",
                job_id=job_id,
                model=self.model,
                file_id=uploaded_id,
            )

            response = await self.client.responses.parse(
                model=self.model,
                instructions=instructions,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_id": uploaded_id},
                            {"type": "input_text", "text": user_text},
                        ],
                    }
                ],
                text_format=ExtractionOutput,
                reasoning={"effort": "low"},
                text={"verbosity": "low"},
                store=False,
            )
        finally:
            if uploaded_id is not None:
                await asyncio.shield(
                    self._delete_uploaded_file(uploaded_id, job_id)
                )

        output = self._parsed_output(response)
        token_usage = usage_to_token_dict(getattr(response, "usage", None))
        cost = estimate_cost_usd(
            self.model,
            input_tokens=token_usage.get("input", 0),
            output_tokens=token_usage.get("output", 0),
            cached_input_tokens=token_usage.get("cached_input", 0),
        )
        logger.info(
            "pdf_vision_extraction_completed",
            job_id=job_id,
            records=len(output.records),
            flagged=len(output.flagged),
            cost_usd=cost,
        )
        return OrchestratorResult(
            extraction=output,
            model=self.model,
            token_usage=token_usage,
            cost_usd=cost,
            agent_seconds=round(time.perf_counter() - t_start, 3),
        )

    async def _delete_uploaded_file(self, file_id: str, job_id: str) -> None:
        try:
            await self.client.files.delete(file_id)
        except Exception:
            logger.warning(
                "pdf_vision_uploaded_file_delete_failed",
                job_id=job_id,
                file_id=file_id,
            )

    @staticmethod
    def _parsed_output(response: Any) -> ExtractionOutput:
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI PDF extraction returned no structured output")
        if isinstance(parsed, ExtractionOutput):
            return parsed
        return ExtractionOutput.model_validate(parsed)
