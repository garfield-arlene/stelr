#!/bin/sh
set -e
export PYTHONPATH=/app
cd /app
exec python -m gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --preload \
    --log-level info \
    app:app
