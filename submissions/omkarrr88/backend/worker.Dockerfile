# syntax=docker/dockerfile:1
# Worker image. Build context: the submission folder (docker build -f backend/worker.Dockerfile .).

FROM python:3.12-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /srv
COPY --from=deps /opt/venv /opt/venv
COPY backend/app ./app
USER app
# The worker has no HTTP port; /health on the API reports its heartbeat instead.
CMD ["python", "-m", "app.worker"]
