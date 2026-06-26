"""Create a clean source submission zip from the current working tree.

Unlike zipping the repository directory, this script includes tracked files plus
safe untracked source files and excludes ignored local artifacts such as `.env`,
runtime PDFs, logs, virtualenvs, node_modules, and build outputs.

Run from the repository root:

    python scripts/create_submission.py
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "medical-billing-records-submission.zip"

ALLOWED_TOP_DIRS = {"backend", "frontend", "docs", "scripts"}
ALLOWED_ROOT_FILES = {
    "README.md", "ASSIGNMENT.md", "AGENTS.md", "SECURITY.md", "LICENSE",
    "docker-compose.yml", ".env.example", ".gitignore",
    "package.json", "package-lock.json",
}
# Artifacts that live *inside* an allowed dir but must still be excluded.
BLOCKED_PREFIXES = (
    "backend/pdfs/",
    "backend/app/.logs/",
    "backend/__pycache__",
    "backend/.venv",
    "backend/.venv-test",
    "backend/.pytest_cache/",
    "frontend/node_modules/",
    "frontend/.next/",
    ".pytest_cache/",
)
# Refuse to ship anything that looks like a live secret (defence in depth).
_SECRET_RE = re.compile(r"sk-(proj-[A-Za-z0-9_-]{8}|[A-Za-z0-9]{20})")


def _git_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [p for p in result.stdout.decode("utf-8").split("\0") if p]


def _allowed(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.endswith(".zip"):
        return False
    if normalized == "backend/pdfs/.gitkeep":
        return True  # keep the shared-volume placeholder
    if any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in BLOCKED_PREFIXES
    ):
        return False
    parts = normalized.split("/")
    if len(parts) == 1:
        return normalized in ALLOWED_ROOT_FILES
    return parts[0] in ALLOWED_TOP_DIRS


def _assert_no_secrets(files: list[str]) -> None:
    leaked = []
    for rel in files:
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            continue
        if _SECRET_RE.search(text):
            leaked.append(rel)
    if leaked:
        raise RuntimeError(
            "Refusing to package: live secret pattern found in: " + ", ".join(leaked)
        )


def create_zip(output: Path) -> int:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = [path for path in _git_files() if _allowed(path)]
    if not files:
        raise RuntimeError("No source files found to package.")

    # Defence in depth: never package a live secret even if one slipped into an
    # allowed source file.
    _assert_no_secrets(files)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(ROOT / rel, rel.replace("\\", "/"))

    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
    blocked = sorted(name for name in names if not _allowed(name))
    if blocked:
        output.unlink(missing_ok=True)
        print("Refusing to keep zip; blocked paths were included:", file=sys.stderr)
        for name in blocked:
            print(f"- {name}", file=sys.stderr)
        return 1

    print(f"Wrote {output}")
    print(f"Included {len(files)} source files.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    return create_zip(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
