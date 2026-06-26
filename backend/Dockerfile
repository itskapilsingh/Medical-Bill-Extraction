FROM python:3.12-slim@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest@sha256:99ea34acedc870ba4ad11a1f540a1c04267c9f30aadc465a94406f52dfda2c36 /uv /uvx /bin/

ENV UV_PYTHON=/usr/local/bin/python3
ENV UV_PYTHON_DOWNLOADS=never

ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml README.md uv.lock ./

RUN uv sync --frozen --no-cache --no-install-project --python /usr/local/bin/python3

COPY . .

RUN chmod +x scripts/migrate.sh

RUN uv sync --frozen --no-cache --python /usr/local/bin/python3

RUN useradd --create-home --uid 1001 appuser \
    && mkdir -p /app/pdfs \
    && chown -R appuser:appuser /app
USER appuser
