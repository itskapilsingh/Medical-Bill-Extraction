"""Backstop PHI sweep for the shared PDF volume.

Jobs delete their own source PDF the moment they reach a terminal state (see
``ExtractionService._delete_pdf``). This sweep is the safety net for the leftovers
that path can't cover: files orphaned by a crash between processing and delete, or
runs with ``DELETE_PDF_AFTER_PROCESSING`` turned off. It is filesystem-only (no DB,
no identity) and intentionally conservative — it removes a file solely on the basis
that its modification time is older than the retention window, which is far longer
than any in-flight job, so it can never race a job that is still being processed.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.common.logger import get_logger
from app.core.common.time import utc_now

logger = get_logger(__name__)


def sweep_expired_pdfs(mount_path: str, retention_days: int) -> int:
    """Delete ``*.pdf`` files under ``mount_path`` older than ``retention_days``.

    Returns the number of files removed. A non-positive ``retention_days``
    disables the sweep (returns 0) so a misconfiguration can never wipe the
    volume wholesale. Never raises — a cleanup error is logged, not propagated.
    """
    if retention_days <= 0:
        return 0

    root = Path(mount_path)
    if not root.is_dir():
        return 0

    cutoff = utc_now().timestamp() - retention_days * 86400
    removed = 0
    try:
        # Recursive: PdfStorage writes to {mount}/{owner}/{uuid}.pdf, so the PDFs
        # live one level below the mount root, not directly under it.
        entries = list(root.rglob("*.pdf"))
    except OSError:
        logger.warning("retention_sweep_list_failed", mount_path=mount_path)
        return 0

    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                os.remove(entry)
                removed += 1
        except FileNotFoundError:
            continue  # raced another deleter — fine
        except OSError:
            # Owner-qualified path, since names collide across owner subdirs.
            logger.warning("retention_sweep_unlink_failed", file=str(entry.relative_to(root)))

    if removed:
        logger.info("retention_sweep", removed=removed, retention_days=retention_days)
    return removed
