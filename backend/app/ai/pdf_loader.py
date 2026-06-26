"""Turn a PDF on the shared volume into the in-memory ``Document`` the agent reads.

We extract layout-aware text per page with pdfplumber. For these billing
documents that linearises the claim/fill tables well enough for the model to read
(amount columns stay on the same logical line as their labels), and it keeps the
loader dependency-light and deterministic. Scanned/image-heavy documents are not
handed to the text agent as partial or empty text; they raise
``VisionExtractionRequired`` so the service can route the original PDF through the
OpenAI PDF-file fallback.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from app.ai.types import Document, Page
from app.core.common.logger import get_logger

logger = get_logger(__name__)

MIN_EXTRACTABLE_CHARS_PER_IMAGE_PAGE = 20
MIN_IMAGE_AREA_RATIO_FOR_VISION = 0.20


class VisionExtractionRequired(ValueError):
    """Raised when pdfplumber text is too incomplete for safe text extraction."""

    def __init__(self, message: str, *, pages: list[int]) -> None:
        super().__init__(message)
        self.pages = pages


def _image_area_ratio(page) -> float:
    page_width = float(getattr(page, "width", 0) or 0)
    page_height = float(getattr(page, "height", 0) or 0)
    page_area = page_width * page_height
    if page_area <= 0:
        return 0.0

    total_image_area = 0.0
    for image in getattr(page, "images", None) or []:
        x0 = float(image.get("x0", 0) or 0)
        x1 = float(image.get("x1", 0) or 0)
        y0 = image.get("top", image.get("y0", 0))
        y1 = image.get("bottom", image.get("y1", 0))
        height = abs(float(y1 or 0) - float(y0 or 0))
        width = abs(x1 - x0)
        total_image_area += width * height
    return total_image_area / page_area


def load_document(pdf_path: str, doc_id: str, max_pages: int | None = None) -> Document:
    """Load ``pdf_path`` into a Document of per-page text.

    Args:
        pdf_path: Absolute path to the PDF on the mounted volume.
        doc_id: Identifier for the run (the job id).
        max_pages: Reject documents with more than this many pages (a cheap guard
            against resource-exhaustion via a hostile/huge PDF). ``None`` = no cap.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file has no readable pages or exceeds ``max_pages``.
        VisionExtractionRequired: If scanned/image-heavy pages need the PDF-file
            OpenAI fallback instead of the text-tool extraction path.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[Page] = []
    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)
        if max_pages is not None and page_count > max_pages:
            raise ValueError(
                f"PDF has {page_count} pages, exceeding the {max_pages}-page limit"
            )
        vision_pages: list[int] = []
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            has_images = bool(getattr(page, "images", None))
            if (
                has_images
                and len(text.strip()) < MIN_EXTRACTABLE_CHARS_PER_IMAGE_PAGE
            ):
                vision_pages.append(index)
            elif has_images and _image_area_ratio(page) >= MIN_IMAGE_AREA_RATIO_FOR_VISION:
                vision_pages.append(index)
            pages.append(Page(page_num=index, page_content=text))

    if not pages:
        raise ValueError(f"PDF has no pages: {pdf_path}")

    non_empty = sum(1 for p in pages if p.page_content.strip())
    if non_empty == 0:
        raise VisionExtractionRequired(
            "PDF has no extractable text; OpenAI PDF vision fallback required",
            pages=[p.page_num for p in pages],
        )
    if vision_pages:
        raise VisionExtractionRequired(
            "PDF contains image-heavy page(s) that require visual extraction; "
            "OpenAI PDF vision fallback required",
            pages=vision_pages,
        )
    logger.info(
        "pdf_loaded",
        doc_id=doc_id,
        pages=len(pages),
        non_empty_pages=non_empty,
    )
    return Document(doc_id=doc_id, num_pages=len(pages), pages=pages)
