FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
# Debian packages ffprobe in ffmpeg; only bounded local inspection uses it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    pkg-config \
    libpq-dev \
    python3-dev \
    curl \
    ffmpeg \
    && /usr/bin/ffprobe -version >/dev/null \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt security-constraints.txt ./
RUN python -m pip install --no-cache-dir --upgrade "pip==26.2.2" \
    && python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for uploads and logs
RUN mkdir -p uploads logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV SOCIAL_MEDIA_FFPROBE_PATH=/usr/bin/ffprobe

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
