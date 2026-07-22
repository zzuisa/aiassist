# syntax=docker/dockerfile:1
# Multi-stage build for the FastAPI monolith. The same image runs the API,
# outbox publisher, Celery workers and Beat.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock.txt
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps .

FROM base AS runtime
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
# Non-root runtime user; asset volume is chowned by an init step in compose.
RUN useradd --system --uid 10001 --home /app appuser \
    && mkdir -p /data/assets \
    && chown -R appuser:appuser /app /data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD python -m app.cli.main healthcheck --url http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
