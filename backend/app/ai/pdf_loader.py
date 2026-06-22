"""Turn a PDF on the shared volume into the in-memory ``Document`` the agent reads.

We extract layout-aware text per page with pdfplumber. For these billing
documents that linearises the claim/fill tables well enough for the model to read
(amount columns stay on the same logical line as their labels), and it keeps the
loader dependency-light and deterministic — no OCR, no vision. Scanned/image-only
pages would come through empty here; that is surfaced as an empty page rather than
guessed at.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from app.ai.types import Document, Page
from app.core.common.logger import get_logger

logger = get_logger(__name__)


def load_document(pdf_path: str, doc_id: str) -> Document:
    """Load ``pdf_path`` into a Document of per-page text.

    Args:
        pdf_path: Absolute path to the PDF on the mounted volume.
        doc_id: Identifier for the run (the job id).

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file has no readable pages.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[Page] = []
    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(Page(page_num=index, page_content=text))

    if not pages:
        raise ValueError(f"PDF has no pages: {pdf_path}")

    non_empty = sum(1 for p in pages if p.page_content.strip())
    logger.info(
        "pdf_loaded",
        doc_id=doc_id,
        pages=len(pages),
        non_empty_pages=non_empty,
    )
    return Document(doc_id=doc_id, num_pages=len(pages), pages=pages)
