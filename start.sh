#!/usr/bin/env bash
set -o errexit

exec python -m uvicorn config.asgi:application --host 0.0.0.0 --port "${PORT:-8000}"
