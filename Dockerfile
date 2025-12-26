# Supernote OCR Enhancer
# Lightweight Debian-based Python container for ARM64 (M4 Mac Mini)

FROM python:3.11-slim-bookworm

LABEL maintainer="liketheduck"
LABEL description="Supernote OCR Enhancer - processes .note files with MLX-VLM OCR"

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set timezone for cron (must be set at build time)
ENV TZ=America/New_York

# Set working directory
WORKDIR /app

# Install system dependencies (including build tools for pycairo, cron, and docker CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    gcc \
    pkg-config \
    libcairo2-dev \
    libfreetype6-dev \
    cron \
    ca-certificates \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    # Configure timezone for cron to use EST/EDT
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

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

# No healthcheck - this is a cron-based service, not a web server

# Default command - run entrypoint script
CMD ["/docker-entrypoint.sh"]
