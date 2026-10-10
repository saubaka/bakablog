#!/bin/sh
set -eu

LABEL="com.saubaka.bakablog"
DOMAIN="gui/$(id -u)"
PLIST_FILE="$HOME/Library/LaunchAgents/${LABEL}.plist"
CONFIG_FILE="${BAKABLOG_MACOS_CONFIG:-$HOME/Library/Application Support/BakaBlog/config/production.env}"
LOG_DIRECTORY="$HOME/Library/Logs/BakaBlog"
ACTION=${1:-status}

[ "$(uname -s)" = "Darwin" ] || {
    printf '%s\n' "manage-macos.sh can only run on macOS." >&2
    exit 1
}

service_loaded() {
    launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

load_config() {
    [ -r "$CONFIG_FILE" ] || return 1
    while IFS='=' read -r key value || [ -n "$key" ]; do
        case "$key" in
            ''|'#'*) continue ;;
            CLOUD_DIARY_ENV|CLOUD_DIARY_SECRET_KEY|CLOUD_DIARY_SITE_URL|CLOUD_DIARY_INSTANCE_PATH|CLOUD_DIARY_TRUST_PROXY_HEADERS|CLOUD_DIARY_TEXT_COMPRESSION|CLOUD_DIARY_PROJECT_DIRECTORY|PORT|WORKERS|THREADS)
                export "$key=$value"
                ;;
            *)
                printf 'Unsupported key in macOS service configuration: %s\n' "$key" >&2
                return 1
                ;;
        esac
    done < "$CONFIG_FILE"
}

start_service() {
    [ -r "$PLIST_FILE" ] || {
        printf 'LaunchAgent is not installed: %s\n' "$PLIST_FILE" >&2
        exit 1
    }
    if ! service_loaded; then
        launchctl bootstrap "$DOMAIN" "$PLIST_FILE"
    fi
    launchctl enable "$DOMAIN/$LABEL"
    launchctl kickstart -k "$DOMAIN/$LABEL"
}

case "$ACTION" in
    start)
        start_service
        printf '%s\n' "baka blog started."
        ;;
    stop)
        if service_loaded; then
            launchctl bootout "$DOMAIN/$LABEL"
        fi
        printf '%s\n' "baka blog stopped; the LaunchAgent file remains installed."
        ;;
    restart)
        if service_loaded; then
            launchctl bootout "$DOMAIN/$LABEL"
        fi
        start_service
        printf '%s\n' "baka blog restarted."
        ;;
    status)
        load_config || true
        if service_loaded; then
            printf '%s\n' "Status: running or scheduled by launchd"
            launchctl print "$DOMAIN/$LABEL" | sed -n '1,35p'
        else
            printf '%s\n' "Status: not loaded"
        fi
        printf 'Site URL: %s\nLoopback: 127.0.0.1:%s\n' \
            "${CLOUD_DIARY_SITE_URL:-unknown}" "${PORT:-unknown}"
        ;;
    doctor)
        load_config || {
            printf 'Configuration file is not readable: %s\n' "$CONFIG_FILE" >&2
            exit 1
        }
        python_path="$CLOUD_DIARY_PROJECT_DIRECTORY/.venv-macos/bin/python"
        [ -x "$python_path" ] || {
            printf 'Virtual environment is missing: %s\n' "$python_path" >&2
            exit 1
        }
        "$python_path" -m pip check
        cd "$CLOUD_DIARY_PROJECT_DIRECTORY"
        "$python_path" -m flask --app wsgi:app system-check
        if service_loaded; then
            site_authority=$("$python_path" -c 'import os; from urllib.parse import urlsplit; print(urlsplit(os.environ["CLOUD_DIARY_SITE_URL"]).netloc)')
            curl --noproxy '*' --fail --silent --show-error \
                --header "Host: $site_authority" \
                --header "X-Forwarded-Host: $site_authority" \
                --header "X-Forwarded-Proto: https" \
                "http://127.0.0.1:${PORT}/healthz"
            printf '\n%s\n' "macOS service health check passed."
        else
            printf '%s\n' "Configuration checks passed; service is not loaded."
        fi
        ;;
    logs)
        mkdir -p "$LOG_DIRECTORY"
        tail -n 100 "$LOG_DIRECTORY/gunicorn-error.log" "$LOG_DIRECTORY/gunicorn-access.log" 2>/dev/null || true
        ;;
    *)
        printf '%s\n' \
            "Usage: manage-macos.sh {start|stop|restart|status|doctor|logs}" >&2
        exit 2
        ;;
esac
