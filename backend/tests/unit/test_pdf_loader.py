import pytest

from app.ai.pdf_loader import load_document


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_document(str(tmp_path / "nope.pdf"), "job-1")


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
