# syntax=docker/dockerfile:1.7

# ---- builder ---------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-only toolchain, kept out of the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip setuptools wheel && pip install .

# ---- runtime ---------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    UPLOAD_DIR=/var/lib/starcode/uploads

# tesseract and poppler are what make OCR of scanned manuscripts work; without them the
# app still runs and says plainly that OCR is unavailable rather than failing silently.
# libpq5 is the runtime half of libpq-dev.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-grc \
        tesseract-ocr-heb \
        tesseract-ocr-ara \
        tesseract-ocr-lat \
        poppler-utils \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Never run as root: a container escape from an application that parses untrusted PDFs
# and images should not land on a privileged shell.
RUN groupadd --system --gid 1001 starcode \
    && useradd --system --uid 1001 --gid starcode --create-home starcode \
    && mkdir -p /var/lib/starcode/uploads \
    && chown -R starcode:starcode /var/lib/starcode

WORKDIR /app
COPY --chown=starcode:starcode alembic.ini ./
COPY --chown=starcode:starcode alembic ./alembic
COPY --chown=starcode:starcode app ./app
COPY --chown=starcode:starcode scripts ./scripts

USER starcode

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
