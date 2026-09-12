# syntax=docker/dockerfile:1

FROM python:3.12.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen


FROM python:3.12.11-slim-bookworm

RUN groupadd --system --gid 10001 sanad \
    && useradd --system --uid 10001 --gid sanad --create-home sanad

WORKDIR /app
COPY --from=builder --chown=sanad:sanad /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SERVER_HOST=0.0.0.0

RUN mkdir -p /app/data && chown sanad:sanad /app/data

USER sanad
EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).read()"]

CMD ["python", "app.py"]
