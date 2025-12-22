#!/bin/bash
set -e

echo "=== Starting Supernote OCR Enhancer ==="
echo "Time: $(date)"
echo "Cron jobs:"
crontab -l

# Start cron in foreground with verbose logging
echo "Starting cron daemon..."
exec cron -f -L 15
