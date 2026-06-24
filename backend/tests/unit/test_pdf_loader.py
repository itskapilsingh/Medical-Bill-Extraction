import pathlib

import pytest

from app.ai.pdf_loader import load_document

_SAMPLE = pathlib.Path(__file__).resolve().parents[3] / "data" / "doc_001.pdf"


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_document(str(tmp_path / "nope.pdf"), "job-1")


def test_max_pages_guard_rejects_oversized():
    """A PDF with more pages than the cap is rejected before extraction.

    Needs a real PDF to open; skips when the git-ignored sample isn't present.
    """
    if not _SAMPLE.exists():
        pytest.skip("sample PDF not present")

    full = load_document(str(_SAMPLE), "job-1")
    # Exactly at the cap is fine; one under the cap is rejected.
    assert load_document(str(_SAMPLE), "job-1", max_pages=full.num_pages)
    with pytest.raises(ValueError, match="exceeding"):
        load_document(str(_SAMPLE), "job-1", max_pages=full.num_pages - 1)


def test_loads_a_real_sample_if_present():
    """If the sample data is present (it is git-ignored), the loader should turn
    it into a Document with per-page text. Skips when the sample isn't checked
    out (e.g. CI without data/)."""
    import pathlib

    sample = pathlib.Path(__file__).resolve().parents[3] / "data" / "doc_001.pdf"
    if not sample.exists():
        pytest.skip("sample PDF not present")

    doc = load_document(str(sample), "job-1")
    assert doc.num_pages > 0
    assert len(doc.pages) == doc.num_pages
    assert any(p.page_content.strip() for p in doc.pages)
