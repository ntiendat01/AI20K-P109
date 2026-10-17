FROM python:3.11-slim

WORKDIR /app

COPY ocr/requirements-ocr.txt ocr/requirements-ocr-service.txt /tmp/ocr/

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libxcb1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check -r /tmp/ocr/requirements-ocr-service.txt \
    && find /usr/local/lib/python3.11/site-packages -type d -name "tests" -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages -type d -name "test" -exec rm -rf {} + \
    && find /usr/local/lib/python3.11/site-packages -name "*.pyc" -delete \
    && find /usr/local/lib/python3.11/site-packages -name "__pycache__" -exec rm -rf {} + \
    && rm -rf /tmp/ocr

RUN python -c "import onnxruntime; print('ONNXRuntime', onnxruntime.__version__)" \
    && python -c "from rapidocr_onnxruntime import RapidOCR; print('RapidOCR import OK')"

COPY src/__init__.py ./src/__init__.py
COPY src/infrastructure/__init__.py ./src/infrastructure/__init__.py
COPY src/infrastructure/ocr ./src/infrastructure/ocr
COPY ocr/ocr_service ./ocr/ocr_service

RUN useradd --create-home appuser \
    && mkdir -p /opt/ocr-models \
    && chown -R appuser:appuser /app /opt/ocr-models

USER appuser

ENV OCR_MODELS_DIR=/opt/ocr-models
ENV PADDLE_PDX_CACHE_HOME=/opt/ocr-models
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ready')" || exit 1

CMD ["uvicorn", "ocr.ocr_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
