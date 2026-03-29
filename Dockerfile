# ── Stage 1: Builder ─────────────────────────────────────────────────────────
# Install deps in a throwaway layer so the final image stays lean.
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y \
    python3-dev build-essential libpq-dev \
    libpq5 python3-psycopg2 \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first — Docker layer caching means this layer
# is only rebuilt when requirements.txt changes, not every code change.
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install \
        -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Don't write .pyc files (faster startup, cleaner image)
ENV PYTHONDONTWRITEBYTECODE=1
# Don't buffer stdout/stderr (logs appear immediately)
ENV PYTHONUNBUFFERED=1

# NEW: Install the runtime PostgreSQL C library
RUN apt-get update \
    && apt-get install -y libpq5 curl\
    && rm -rf /var/lib/apt/lists/*

# Create the mandatory Hugging Face non-root user
RUN useradd -m -u 1000 user

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Switch to the non-root user and set up the working directory
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy source code with correct user ownership
COPY --chown=user:user src/ ./src/
COPY --chown=user:user ingest.py analyze.py seed_test_data.py ./
COPY --chown=user:user dashboard/ ./dashboard/

# Expose FastAPI port
EXPOSE 8000 7860

# Health check — Docker will restart the container if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" && curl -f http://localhost:7860/_stcore/health || exit 1

# Run the API with uvicorn
# --host 0.0.0.0 makes it reachable from outside the container
# --workers 1 because SQLite doesn't handle multiple writers well
CMD uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 1 & \
    sleep 2 && \
    streamlit run dashboard/Home.py \
      --server.port=7860 \
      --server.address=0.0.0.0 \
      --server.headless=true \
      --browser.gatherUsageStats=false
