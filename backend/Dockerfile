FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Match the base image interpreter; avoid uv downloading a newer managed Python on `uv sync`
ENV UV_PYTHON=/usr/local/bin/python3
ENV UV_PYTHON_DOWNLOADS=never

# uv sync installs into .venv — put tools on PATH for migrate.sh / compose commands
ENV PATH="/app/.venv/bin:$PATH"

# Dependency resolution is pinned by uv.lock (regenerate with: uv lock --python 3.12)
COPY pyproject.toml README.md uv.lock ./

RUN uv sync --frozen --no-cache --no-install-project --python /usr/local/bin/python3

COPY . .

# Ensure the migration entrypoint is executable regardless of how git recorded it.
RUN chmod +x scripts/migrate.sh

RUN uv sync --frozen --no-cache --python /usr/local/bin/python3

# Drop root. Create the PDF mount dir up front and hand the whole app tree (the
# venv and /app/pdfs included) to the non-root user, so the named volume mounted
# at /app/pdfs inherits writable ownership and the API/worker can persist uploads.
RUN useradd --create-home --uid 1001 appuser \
    && mkdir -p /app/pdfs \
    && chown -R appuser:appuser /app
USER appuser
