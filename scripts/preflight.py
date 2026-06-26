"""Submission/production-safety preflight checks.

Run from the repository root before packaging or sharing the project:

    python scripts/preflight.py

The check intentionally fails on local runtime artifacts that are normal during
development but unsafe in a submission bundle: secrets, uploaded PDFs, build
outputs, logs, virtualenvs, and an unfinished design document.
"""
from __future__ import annotations

import sys
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

BLOCKED_PATHS = [
    ".env",
    "backend/.venv",
    "backend/.venv-test",
    "frontend/.next",
    "frontend/node_modules",
    ".pytest_cache",
    "backend/.pytest_cache",
    "frontend/.vitest",
]

BLOCKED_GLOBS = [
    "backend/pdfs/*",
    "backend/app/.logs/*",
    "*.log",
    "backend/*.log",
    "frontend/*.log",
    "*.zip",
]

DESIGN_PLACEHOLDERS = [
    "[date]",
    "[approximate hours",
]
PAXEL_PLACEHOLDER = re.compile(
    r"Paxel report URL:\**\s*(?:$|not generated|todo|tbd)",
    re.IGNORECASE | re.MULTILINE,
)


def _is_allowed_runtime_file(path: Path) -> bool:
    return path.as_posix() == "backend/pdfs/.gitkeep"


def main() -> int:
    failures: list[str] = []

    for rel in BLOCKED_PATHS:
        path = ROOT / rel
        if path.exists():
            failures.append(f"remove local-only artifact: {rel}")

    for pattern in BLOCKED_GLOBS:
        for path in ROOT.glob(pattern):
            rel = path.relative_to(ROOT)
            if path.exists() and not _is_allowed_runtime_file(rel):
                failures.append(f"remove local-only artifact: {rel.as_posix()}")

    design = ROOT / "docs" / "design.md"
    if design.exists():
        text = design.read_text(encoding="utf-8")
        for placeholder in DESIGN_PLACEHOLDERS:
            if placeholder in text:
                failures.append(
                    "complete docs/design.md by hand before submission "
                    f"(found {placeholder!r})"
                )
                break
        if PAXEL_PLACEHOLDER.search(text):
            failures.append("add the Paxel report URL to docs/design.md")
    else:
        failures.append("docs/design.md is missing")

    if failures:
        print("Preflight failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
