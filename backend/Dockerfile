# syntax=docker/dockerfile:1
# Multi-stage build for the FastAPI monolith. The same image runs the API,
# outbox publisher, Celery workers and Beat. psycopg[binary] bundles libpq and
# the healthcheck uses Python, so no apt packages are required at runtime.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS builder
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
# Non-root runtime user; the asset volume is writable by this uid in compose.
RUN useradd --system --uid 10001 --home /app appuser \
    && mkdir -p /data/assets \
    && chown -R appuser:appuser /app /data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-m", "app.cli.main", "healthcheck", "--url", "http://localhost:8000/health/live"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
