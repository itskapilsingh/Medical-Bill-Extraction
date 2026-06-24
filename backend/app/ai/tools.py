"""Tools the extraction agent uses to navigate a document.

Design intent (see docs/design.md §3): the document can be large (100+ pages) and
mostly noise, so we do NOT dump every page into the context. Instead the agent
gets read-only navigation tools over the loaded ``Document`` and pulls only the
pages it needs:

- ``list_pages``   — the outline (page number + heuristic kind + snippet) so it can
                     locate billing pages and skip cover/lab/prescription noise.
- ``read_pages``   — full text of specific pages (and ranges, for tables that span
                     pages).
- ``search_document`` — find pages containing a phrase (e.g. "Claim Total",
                     "TOTALS"), to jump to summary lines.

Each tool's logic lives in a plain helper (``outline_text`` / ``read_pages_text``
/ ``search_text``) so it is unit-testable without the agent runtime; the
``@function_tool`` wrappers just bind ``ctx.context.document``. The document is
never mutated — the agent's only state is its own message history.
"""

from __future__ import annotations

from agents import function_tool
from agents.tool_context import ToolContext

from app.ai.context import RunContext
from app.ai.page_kinds import classify_page
from app.ai.types import Document

_SNIPPET_CHARS = 100


def _snippet(text: str, limit: int = _SNIPPET_CHARS) -> str:
    return " ".join(text.split())[:limit]


# ------------------------------------------------------------------ pure logic


def outline_text(document: Document) -> str:
    """Render the per-page outline (number, heuristic kind, snippet)."""
    lines = [f"Document '{document.doc_id}' has {document.num_pages} page(s):"]
    for page in document.pages:
        kind = classify_page(page.page_content)
        lines.append(f"p{page.page_num} [{kind}] {_snippet(page.page_content)}")
    return "\n".join(lines)


def read_pages_text(document: Document, page_numbers: list[int]) -> str:
    """Render the full text of the requested pages, in order, with markers."""
    pages = {p.page_num: p for p in document.pages}
    chunks: list[str] = []
    for number in page_numbers:
        page = pages.get(number)
        if page is None:
            chunks.append(f"=== page {number} === (out of range)")
        else:
            body = page.page_content.strip() or "(no extractable text on this page)"
            chunks.append(f"=== page {number} ===\n{body}")
    return "\n\n".join(chunks) if chunks else "(no pages requested)"


def search_text(document: Document, query: str) -> str:
    """Render the pages whose text contains ``query`` (case-insensitive)."""
    needle = query.lower().strip()
    if not needle:
        return "(empty query)"
    hits: list[str] = []
    for page in document.pages:
        if needle in page.page_content.lower():
            hits.append(f"p{page.page_num}: {_snippet(page.page_content, 140)}")
    if not hits:
        return f"No pages contain '{query}'."
    return f"'{query}' found on {len(hits)} page(s):\n" + "\n".join(hits)


# --------------------------------------------------------------- agent tools


@function_tool
async def list_pages(ctx: ToolContext[RunContext]) -> str:
    """Outline the document so you can locate the billing pages.

    Returns one line per page: the page number, a heuristic kind in brackets, and
    a short snippet. Kinds are advisory — verify by reading. Skip ``cover``,
    ``certification``, ``lab_report``, and ``prescription`` pages; extract from
    ``billing_ledger`` and ``pharmacy_ledger`` pages.

    Returns:
        A newline-delimited outline of every page.
    """
    return outline_text(ctx.context.document)


@function_tool
async def read_pages(ctx: ToolContext[RunContext], page_numbers: list[int]) -> str:
    """Return the full text of one or more pages, in order.

    Use this to read the billing pages you identified from ``list_pages``. Pass
    consecutive page numbers when a table continues across pages so you can follow
    a claim or fill list that splits at a page break.

    Args:
        page_numbers: 1-based page numbers to read (e.g. [6, 7, 8]).

    Returns:
        The pages' text, each prefixed with a ``=== page N ===`` marker.
    """
    return read_pages_text(ctx.context.document, page_numbers)


@function_tool
async def search_document(ctx: ToolContext[RunContext], query: str) -> str:
    """Find pages whose text contains ``query`` (case-insensitive).

    Useful for jumping to summary lines — e.g. search "Claim Total" or "TOTALS"
    to find the per-claim or document totals that drive the amount fields.

    Args:
        query: Substring to look for.

    Returns:
        Matching page numbers with a snippet around context, or a no-match note.
    """
    return search_text(ctx.context.document, query)
