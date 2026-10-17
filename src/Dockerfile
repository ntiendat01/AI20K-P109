# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements-core.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --prefix=/install -r requirements-core.txt


# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local
RUN useradd -m appuser


COPY src ./src

RUN mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
