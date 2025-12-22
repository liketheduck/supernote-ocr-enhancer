# Supernote OCR Enhancer
# Lightweight Debian-based Python container for ARM64 (M4 Mac Mini)

FROM python:3.11-slim-bookworm

LABEL maintainer="liketheduck"
LABEL description="Supernote OCR Enhancer - processes .note files with MLX-VLM OCR"

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Install system dependencies (including build tools for pycairo and cron)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    pkg-config \
    libcairo2-dev \
    libfreetype6-dev \
    cron \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better caching
COPY app/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and scripts
COPY app/ /app/
COPY scripts/ /app/scripts/
COPY run-with-sync-control.sh /app/
COPY config/crontab /tmp/crontab.tmp
COPY docker-entrypoint.sh /docker-entrypoint.sh

# Set up cron
RUN chmod +x /app/scripts/*.sh /app/run-with-sync-control.sh /docker-entrypoint.sh \
    && crontab /tmp/crontab.tmp \
    && rm /tmp/crontab.tmp \
    && touch /var/log/cron.log

# Create non-root user for security (but run cron as root since it needs docker access)
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app \
    && mkdir -p /app/data && chown -R appuser:appuser /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command - run entrypoint script
CMD ["/docker-entrypoint.sh"]
