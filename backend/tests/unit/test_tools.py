"""The agent's navigation tools — the AI axis the assignment weights highly.
Logic is exercised through the plain helpers the @function_tool wrappers call."""

from app.ai.tools import outline_text, read_pages_text, search_text
from app.ai.types import Document, Page

DOC = Document(
    doc_id="doc_x",
    num_pages=3,
    pages=[
        Page(page_num=1, page_content="Billing Summary\nClaim ID 123\nClaim Total: $500.00"),
        Page(page_num=2, page_content="Laboratory Report\nTest Name Value Reference Range"),
        Page(page_num=3, page_content="RX # FILL DATE NDC CHARGE 3RD PARTY\nTOTALS: $9"),
    ],
)


def test_outline_labels_each_page_with_a_kind():
    out = outline_text(DOC)
    assert "Document 'doc_x' has 3 page(s)" in out
    assert "p1 [billing_ledger]" in out
    assert "p2 [lab_report]" in out
    assert "p3 [pharmacy_ledger]" in out


def test_read_pages_returns_requested_pages_in_order_with_markers():
    out = read_pages_text(DOC, [1, 3])
    assert "=== page 1 ===" in out and "Claim Total" in out
    assert "=== page 3 ===" in out and "TOTALS" in out
    # order preserved
    assert out.index("=== page 1 ===") < out.index("=== page 3 ===")


def test_read_pages_handles_out_of_range():
    out = read_pages_text(DOC, [99])
    assert "=== page 99 === (out of range)" in out


def test_read_pages_empty_request():
    assert read_pages_text(DOC, []) == "(no pages requested)"


def test_search_finds_pages_case_insensitively():
    out = search_text(DOC, "claim total")
    assert "p1:" in out
    assert "p2:" not in out


def test_search_no_match_and_empty_query():
    assert "No pages contain" in search_text(DOC, "zzz-not-here")
    assert search_text(DOC, "   ") == "(empty query)"
