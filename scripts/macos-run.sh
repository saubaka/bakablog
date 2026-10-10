#!/bin/sh
set -eu

[ "$(uname -s)" = "Darwin" ] || {
    printf '%s\n' "macos-run.sh can only run on macOS." >&2
    exit 1
}
[ "$#" -eq 1 ] || {
    printf '%s\n' "Usage: macos-run.sh /absolute/path/to/production.env" >&2
    exit 2
}

CONFIG_FILE=$1
[ -r "$CONFIG_FILE" ] || {
    printf 'Configuration file is not readable: %s\n' "$CONFIG_FILE" >&2
    exit 1
}

while IFS='=' read -r key value || [ -n "$key" ]; do
    case "$key" in
        ''|'#'*) continue ;;
        CLOUD_DIARY_ENV|CLOUD_DIARY_SECRET_KEY|CLOUD_DIARY_SITE_URL|CLOUD_DIARY_INSTANCE_PATH|CLOUD_DIARY_TRUST_PROXY_HEADERS|CLOUD_DIARY_TEXT_COMPRESSION|CLOUD_DIARY_PROJECT_DIRECTORY|PORT|WORKERS|THREADS)
            export "$key=$value"
            ;;
        *)
            printf 'Unsupported key in macOS service configuration: %s\n' "$key" >&2
            exit 1
            ;;
    esac
done < "$CONFIG_FILE"

: "${CLOUD_DIARY_PROJECT_DIRECTORY:?CLOUD_DIARY_PROJECT_DIRECTORY is required}"
: "${CLOUD_DIARY_SECRET_KEY:?CLOUD_DIARY_SECRET_KEY is required}"
: "${CLOUD_DIARY_SITE_URL:?CLOUD_DIARY_SITE_URL is required}"
: "${CLOUD_DIARY_INSTANCE_PATH:?CLOUD_DIARY_INSTANCE_PATH is required}"
: "${PORT:?PORT is required}"

case "$CLOUD_DIARY_PROJECT_DIRECTORY" in
    /*) ;;
    *) printf '%s\n' "CLOUD_DIARY_PROJECT_DIRECTORY must be absolute." >&2; exit 1 ;;
esac

cd "$CLOUD_DIARY_PROJECT_DIRECTORY"
exec "$CLOUD_DIARY_PROJECT_DIRECTORY/.venv-macos/bin/gunicorn" \
    --bind "127.0.0.1:${PORT}" \
    --workers "${WORKERS:-2}" \
    --threads "${THREADS:-4}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    wsgi:app
