import pathlib

import pytest

from app.ai.pdf_loader import VisionExtractionRequired, load_document

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


def test_image_only_pdf_routes_to_vision_fallback(monkeypatch, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    class FakePage:
        images = [{"name": "scan"}]

        def extract_text(self):
            return ""

    class FakePdf:
        pages = [FakePage(), FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.ai.pdf_loader.pdfplumber.open", lambda _: FakePdf())

    with pytest.raises(VisionExtractionRequired, match="no extractable text") as exc:
        load_document(str(pdf), "job-scan")
    assert exc.value.pages == [1, 2]


def test_sparse_image_page_routes_to_vision_fallback(monkeypatch, tmp_path):
    pdf = tmp_path / "mixed.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    class TextPage:
        images = []
        width = 600
        height = 800

        def extract_text(self):
            return "Billing Summary\nClaim ID INV-100\nClaim Total: 10 8 1 1"

    class ScreenshotPage:
        images = [{"name": "software-screenshot"}]
        width = 600
        height = 800

        def extract_text(self):
            return "Total"

    class FakePdf:
        pages = [TextPage(), ScreenshotPage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.ai.pdf_loader.pdfplumber.open", lambda _: FakePdf())

    with pytest.raises(VisionExtractionRequired, match="visual extraction") as exc:
        load_document(str(pdf), "job-mixed")
    assert exc.value.pages == [2]


def test_large_screenshot_with_some_text_routes_to_vision_fallback(monkeypatch, tmp_path):
    pdf = tmp_path / "screenshot.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    class ScreenshotPage:
        width = 600
        height = 800
        images = [{"x0": 30, "x1": 570, "top": 120, "bottom": 720}]

        def extract_text(self):
            return "Patient billing portal export for account INV-200"

    class FakePdf:
        pages = [ScreenshotPage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.ai.pdf_loader.pdfplumber.open", lambda _: FakePdf())

    with pytest.raises(VisionExtractionRequired, match="visual extraction") as exc:
        load_document(str(pdf), "job-screenshot")
    assert exc.value.pages == [1]


def test_blank_non_image_page_does_not_force_vision(monkeypatch, tmp_path):
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    class BlankPage:
        images = []
        width = 600
        height = 800

        def extract_text(self):
            return ""

    class TextPage:
        images = []
        width = 600
        height = 800

        def extract_text(self):
            return "Billing Summary\nClaim ID INV-100\nClaim Total: 10 8 1 1"

    class FakePdf:
        pages = [BlankPage(), TextPage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.ai.pdf_loader.pdfplumber.open", lambda _: FakePdf())

    doc = load_document(str(pdf), "job-blank")
    assert doc.num_pages == 2
    assert doc.pages[1].page_content.startswith("Billing Summary")
