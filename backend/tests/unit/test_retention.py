import os

from app.worker.retention import sweep_expired_pdfs


def _write(path, mtime_days_ago: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 x")
    ts = os.path.getmtime(path) - mtime_days_ago * 86400
    os.utime(path, (ts, ts))


def test_removes_only_files_older_than_retention(tmp_path):
    # Mirror the production layout: PdfStorage writes {mount}/{owner}/{uuid}.pdf,
    # so the sweep must recurse into the per-owner subdirectories.
    old = tmp_path / "owner-a" / "old.pdf"
    fresh = tmp_path / "owner-b" / "fresh.pdf"
    _write(old, mtime_days_ago=40)
    _write(fresh, mtime_days_ago=1)

    removed = sweep_expired_pdfs(str(tmp_path), retention_days=30)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()


def test_recurses_into_nested_owner_dirs(tmp_path):
    # Regression guard: a non-recursive glob would miss this and reap nothing.
    expired = tmp_path / "user-123" / "abc.pdf"
    _write(expired, mtime_days_ago=99)

    assert sweep_expired_pdfs(str(tmp_path), retention_days=30) == 1
    assert not expired.exists()


def test_ignores_non_pdf_files(tmp_path):
    keep = tmp_path / "notes.txt"
    keep.write_text("keep me")
    os.utime(keep, (0, 0))  # ancient, but not a .pdf

    assert sweep_expired_pdfs(str(tmp_path), retention_days=1) == 0
    assert keep.exists()


def test_non_positive_retention_is_a_noop(tmp_path):
    old = tmp_path / "old.pdf"
    _write(old, mtime_days_ago=999)

    assert sweep_expired_pdfs(str(tmp_path), retention_days=0) == 0
    assert old.exists()


def test_missing_directory_returns_zero(tmp_path):
    assert sweep_expired_pdfs(str(tmp_path / "nope"), retention_days=30) == 0
