FROM python:3.12-slim

# Prevents Python from writing .pyc files and forces stdout/stderr to be unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (minimal); playwright --with-deps will install remaining runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (use project-root paths)
COPY etl/requirements.txt /app/etl/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade "pip==26.2.2" \
    && python -m pip install --no-cache-dir -r /app/etl/requirements.txt \
    && python -m playwright install chromium firefox --with-deps

# Copy full project (so package path `etl.*` exists)
COPY . /app/

# Create non-root user and set permissions for writable paths
RUN useradd -u 10001 -m etluser \
    && mkdir -p /app/downloads /app/logs \
    && chown -R etluser:etluser /app/downloads /app/logs

# Switch to non-root user
USER etluser

# Helpful envs
ENV PYTHONPATH=/app \
    PLAYWRIGHT_ENABLED=1

# Run the scheduler/worker
ENTRYPOINT ["python", "-m", "etl.worker"]
