"""Filesystem storage for uploaded PDFs on the shared volume.

The volume is mounted into both the API (which writes) and the worker (which
reads) at ``PDF_MOUNT_PATH``. Files are laid out per owner — ``{mount}/{owner}/
{uuid}.pdf`` — which keeps one user's uploads out of another's directory as a
small defence-in-depth measure alongside the database's RLS. The database, not
the filesystem, is the isolation boundary; this is just tidy.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

# Better Auth ids are URL-safe, but guard the path component anyway.
_SAFE = re.compile(r"[^A-Za-z0-9_-]")

PDF_MAGIC = b"%PDF-"


class InvalidPdfError(ValueError):
    """Raised when an upload is not a usable PDF."""


class PdfStorage:
    def __init__(self, mount_path: str) -> None:
        self._root = Path(mount_path)

    def _safe(self, value: str) -> str:
        cleaned = _SAFE.sub("_", value)
        return cleaned or "unknown"

    def fingerprint(self, data: bytes) -> str:
        """SHA-256 of the file bytes — the content identity used for caching."""
        return hashlib.sha256(data).hexdigest()

    def validate(self, data: bytes) -> None:
        """Validate that ``data`` looks like a PDF before it is persisted."""
        if not data:
            raise InvalidPdfError("Uploaded file is empty.")
        if not data.startswith(PDF_MAGIC):
            raise InvalidPdfError("Uploaded file is not a PDF (missing %PDF header).")

    def save(self, *, owner_id: str, data: bytes) -> tuple[str, str]:
        """Persist ``data`` for ``owner_id``. Returns ``(absolute_path, sha256)``.

        Raises InvalidPdfError if the bytes are empty or do not start with the
        PDF magic number.
        """
        self.validate(data)

        digest = self.fingerprint(data)
        owner_dir = self._root / self._safe(owner_id)
        owner_dir.mkdir(parents=True, exist_ok=True)
        path = owner_dir / f"{uuid.uuid4().hex}.pdf"
        path.write_bytes(data)
        return str(path), digest

    def delete(self, pdf_path: str | None) -> bool:
        """Delete one stored PDF if it is inside the configured mount.

        Returns True when a file was removed. Missing files are treated as a
        successful no-op. A path outside the mount is rejected instead of blindly
        unlinking it; callers may pass DB values, so keep the filesystem boundary
        explicit.
        """
        if not pdf_path:
            return False

        root = self._root.resolve()
        path = Path(pdf_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise InvalidPdfError("Refusing to delete a PDF outside the storage root.") from exc

        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
