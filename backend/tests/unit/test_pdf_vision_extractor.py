from types import SimpleNamespace

import pytest

from app.ai.pdf_vision_extractor import PdfVisionExtractor
from app.models.extraction import BillingRecord, ExtractionOutput


class FakeFiles:
    def __init__(self):
        self.created = None
        self.deleted = []

    async def create(self, *, file, purpose):
        self.created = {"purpose": purpose, "bytes": file.read()}
        return SimpleNamespace(id="file-abc")

    async def delete(self, file_id):
        self.deleted.append(file_id)


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.parse_kwargs = None

    async def parse(self, **kwargs):
        self.parse_kwargs = kwargs
        return SimpleNamespace(
            output_parsed=self.output,
            usage=SimpleNamespace(input_tokens=30, output_tokens=12, total_tokens=42),
        )


class FakeClient:
    def __init__(self, output):
        self.files = FakeFiles()
        self.responses = FakeResponses(output)


@pytest.mark.asyncio
async def test_pdf_vision_extractor_uploads_pdf_and_requests_structured_output(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake")
    output = ExtractionOutput(
        records=[
            BillingRecord(
                invoice_number="INV-100",
                treatment_date="01/01/2024",
                cpt_codes=["99213"],
                provider="Vision Clinic",
                total_charges=100.0,
                page="1",
            )
        ]
    )
    client = FakeClient(output)

    result = await PdfVisionExtractor(client=client).run(
        pdf_path=str(pdf), job_id="job-scan"
    )

    assert result.extraction.records[0].invoice_number == "INV-100"
    assert result.model == "gpt-5.4-mini"
    assert "-pro" not in result.model
    assert result.token_usage == {"input": 30, "output": 12, "total": 42}
    assert client.files.created["purpose"] == "user_data"
    assert client.files.created["bytes"].startswith(b"%PDF-1.4")
    assert client.files.deleted == ["file-abc"]

    kwargs = client.responses.parse_kwargs
    assert kwargs["model"] == "gpt-5.4-mini"
    assert kwargs["text_format"] is ExtractionOutput
    assert kwargs["store"] is False
    assert kwargs["reasoning"] == {"effort": "low"}
    assert kwargs["text"] == {"verbosity": "low"}
    content = kwargs["input"][0]["content"]
    assert {"type": "input_file", "file_id": "file-abc"} in content
    assert any(part["type"] == "input_text" for part in content)
