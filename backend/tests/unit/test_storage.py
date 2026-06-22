import hashlib

import pytest

from app.core.storage import InvalidPdfError, PdfStorage


def test_rejects_non_pdf(tmp_path):
    storage = PdfStorage(str(tmp_path))
    with pytest.raises(InvalidPdfError):
        storage.save(owner_id="user-1", data=b"this is not a pdf")


def test_rejects_empty_upload(tmp_path):
    storage = PdfStorage(str(tmp_path))
    with pytest.raises(InvalidPdfError):
        storage.save(owner_id="user-1", data=b"")


def test_saves_pdf_under_owner_dir_and_fingerprints(tmp_path):
    storage = PdfStorage(str(tmp_path))
    data = b"%PDF-1.7\n%binary\n... content ..."
    path, digest = storage.save(owner_id="user-1", data=data)

    assert digest == hashlib.sha256(data).hexdigest()
    assert "user-1" in path
    with open(path, "rb") as fh:
        assert fh.read() == data


def test_owner_dirs_isolate_uploads(tmp_path):
    storage = PdfStorage(str(tmp_path))
    p1, _ = storage.save(owner_id="alice", data=b"%PDF-1.4 a")
    p2, _ = storage.save(owner_id="bob", data=b"%PDF-1.4 b")
    assert "alice" in p1 and "bob" in p2
    assert p1 != p2


def test_fingerprint_is_content_addressed(tmp_path):
    storage = PdfStorage(str(tmp_path))
    assert storage.fingerprint(b"same") == storage.fingerprint(b"same")
    assert storage.fingerprint(b"a") != storage.fingerprint(b"b")
