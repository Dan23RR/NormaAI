# ============================================================
# NormaAI — Multi-stage Dockerfile for production deployment
# ============================================================

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir poetry==1.8.5

WORKDIR /app
COPY pyproject.toml poetry.lock* ./

# Generate lock file if missing, then export to requirements.txt.
# Include the `openrouter` extra so langchain-openai (the OpenRouter/OpenAI-
# compatible provider, imported lazily in src/agents/llm.py) ships in the image
# — without it the openrouter path fails at runtime with ModuleNotFoundError.
RUN poetry lock --no-update --no-interaction 2>/dev/null || true && \
    poetry export -f requirements.txt --without-hashes --no-interaction --only main --extras openrouter > requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Security: non-root user
RUN groupadd -r normaai && useradd -r -g normaai -d /app -s /sbin/nologin normaai

WORKDIR /app

# Install system dependencies for lxml, psycopg, and health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image BEFORE copying the app code, so that
# source changes don't invalidate this ~1.1 GB download layer (fast rebuilds).
# The runtime container is read-only, so fastembed cannot fetch the model at
# first use; it caches by $HOME (differs build-root vs runtime-normaai), so we
# pin an explicit FASTEMBED_CACHE_DIR used identically here and by the indexer.
# Runtime loads it offline from the in-image copy.
ENV FASTEMBED_CACHE_DIR=/app/models
RUN python -c "from fastembed import TextEmbedding; \
    TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-mpnet-base-v2', cache_dir='/app/models')"

# Copy application code (changes here no longer trigger a model re-download)
COPY src/ src/
COPY prompts/ prompts/
COPY scripts/ scripts/

# Set ownership (covers the baked model cache too)
RUN chown -R normaai:normaai /app

USER normaai

# Environment. HF_HUB_OFFLINE=1 keeps the read-only runtime from attempting any
# network/lock writes — it loads the baked model purely from the local cache.
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
