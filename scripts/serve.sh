#!/usr/bin/env sh
set -eu

: "${CLOUD_DIARY_SECRET_KEY:?CLOUD_DIARY_SECRET_KEY is required}"
: "${CLOUD_DIARY_SITE_URL:?CLOUD_DIARY_SITE_URL is required}"
: "${CLOUD_DIARY_INSTANCE_PATH:?CLOUD_DIARY_INSTANCE_PATH is required}"

export CLOUD_DIARY_ENV=production
export CLOUD_DIARY_TRUST_PROXY_HEADERS="${CLOUD_DIARY_TRUST_PROXY_HEADERS:-1}"
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-2}"
THREADS="${THREADS:-4}"

exec .venv/bin/gunicorn --bind "127.0.0.1:${PORT}" --workers "${WORKERS}" --threads "${THREADS}" --timeout 120 --access-logfile - --error-logfile - wsgi:app
