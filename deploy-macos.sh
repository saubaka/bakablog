#!/bin/sh
set -eu

LABEL="com.saubaka.bakablog"
REPOSITORY_URL="https://github.com/saubaka/bakablog.git"
BRANCH="main"
APP_SUPPORT_DIRECTORY="$HOME/Library/Application Support/BakaBlog"
PROJECT_DIRECTORY="$APP_SUPPORT_DIRECTORY/current"
INSTANCE_DIRECTORY="$APP_SUPPORT_DIRECTORY/instance"
CONFIG_FILE="$APP_SUPPORT_DIRECTORY/config/production.env"
PLIST_FILE="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIRECTORY="$HOME/Library/Logs/BakaBlog"
SITE_URL=""
PORT="8080"
PYTHON_REQUESTED=""
SOURCE_MODE="remote"
OFFLINE=0
CHECK_ONLY=0
NO_START=0
SITE_URL_SET=0
INSTANCE_DIRECTORY_SET=0
PORT_SET=0
SCRIPT_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
    printf '%s\n' \
        "Usage: ./deploy-macos.sh [options]" \
        "" \
        "  --site-url URL       Required HTTPS public origin" \
        "  --repo URL           Git repository (default: ${REPOSITORY_URL})" \
        "  --branch NAME        Git branch (default: ${BRANCH})" \
        "  --project-dir PATH   Deployment checkout (default: ~/Library/Application Support/BakaBlog/current)" \
        "  --instance-dir PATH  Persistent instance data directory" \
        "  --port NUMBER        Fixed loopback Gunicorn port (default: 8080)" \
        "  --python PATH        Python 3.11-3.14 executable" \
        "  --local              Deploy the checkout containing this script" \
        "  --offline            Install only from the checkout wheelhouse" \
        "  --no-start           Install and validate without loading LaunchAgent" \
        "  --check-only         Validate macOS, arguments and source without writes" \
        "  --help               Show this help"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --site-url)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --site-url." >&2; exit 2; }
            SITE_URL=$2
            SITE_URL_SET=1
            shift 2
            ;;
        --repo)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --repo." >&2; exit 2; }
            REPOSITORY_URL=$2
            shift 2
            ;;
        --branch)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --branch." >&2; exit 2; }
            BRANCH=$2
            shift 2
            ;;
        --project-dir)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --project-dir." >&2; exit 2; }
            PROJECT_DIRECTORY=$2
            shift 2
            ;;
        --instance-dir)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --instance-dir." >&2; exit 2; }
            INSTANCE_DIRECTORY=$2
            INSTANCE_DIRECTORY_SET=1
            shift 2
            ;;
        --port)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --port." >&2; exit 2; }
            PORT=$2
            PORT_SET=1
            shift 2
            ;;
        --python)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --python." >&2; exit 2; }
            PYTHON_REQUESTED=$2
            shift 2
            ;;
        --local)
            SOURCE_MODE="local"
            PROJECT_DIRECTORY=$SCRIPT_DIRECTORY
            shift
            ;;
        --offline)
            OFFLINE=1
            shift
            ;;
        --no-start)
            NO_START=1
            shift
            ;;
        --check-only)
            CHECK_ONLY=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[ "$(uname -s)" = "Darwin" ] || {
    printf '%s\n' "This installer only supports macOS." >&2
    exit 1
}
[ "$(id -u)" -ne 0 ] || {
    printf '%s\n' "Run this installer as the signed-in macOS user, without sudo." >&2
    exit 1
}

case "$REPOSITORY_URL" in
    https://*) ;;
    *) printf '%s\n' "Repository URL must use HTTPS." >&2; exit 2 ;;
esac
case "$BRANCH" in
    ''|-*|*..*|*[!A-Za-z0-9._/-]*) printf '%s\n' "Invalid branch name." >&2; exit 2 ;;
esac
case "$PROJECT_DIRECTORY" in
    /*) ;;
    *) printf '%s\n' "Project directory must be absolute." >&2; exit 2 ;;
esac
case "$INSTANCE_DIRECTORY" in
    /*) ;;
    *) printf '%s\n' "Instance directory must be absolute." >&2; exit 2 ;;
esac
if [ "$PROJECT_DIRECTORY" = "/" ] || [ "$PROJECT_DIRECTORY" = "$HOME" ] || [ "$PROJECT_DIRECTORY" = "$APP_SUPPORT_DIRECTORY" ]; then
    printf '%s\n' "Refusing to use a broad directory as the project checkout." >&2
    exit 2
fi

find_python() {
    if [ -n "$PYTHON_REQUESTED" ]; then
        candidates=$PYTHON_REQUESTED
    else
        candidates="/opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 python3.14 python3.13 python3.12 python3.11 python3"
    fi
    for candidate in $candidates; do
        resolved=$(command -v "$candidate" 2>/dev/null || true)
        [ -n "$resolved" ] || continue
        if "$resolved" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] < (3, 15)))' 2>/dev/null; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done
    return 1
}

PYTHON_BINARY=$(find_python || true)
[ -n "$PYTHON_BINARY" ] || {
    printf '%s\n' \
        "Python 3.11-3.14 is required." \
        "Install it with Homebrew (for example: brew install python@3.14)," \
        "or pass an existing interpreter with --python PATH." >&2
    exit 1
}

for required_command in git curl launchctl; do
    command -v "$required_command" >/dev/null 2>&1 || {
        printf 'Required command is missing: %s\n' "$required_command" >&2
        exit 1
    }
done

read_config_value() {
    config_key=$1
    [ -r "$CONFIG_FILE" ] || return 0
    awk -F= -v wanted="$config_key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$CONFIG_FILE"
}

if [ "$SITE_URL_SET" -eq 0 ]; then
    SITE_URL=$(read_config_value CLOUD_DIARY_SITE_URL)
fi
if [ "$INSTANCE_DIRECTORY_SET" -eq 0 ]; then
    existing_instance=$(read_config_value CLOUD_DIARY_INSTANCE_PATH)
    [ -z "$existing_instance" ] || INSTANCE_DIRECTORY=$existing_instance
fi
if [ "$PORT_SET" -eq 0 ]; then
    existing_port=$(read_config_value PORT)
    [ -z "$existing_port" ] || PORT=$existing_port
fi

[ -n "$SITE_URL" ] || {
    printf '%s\n' "A production HTTPS origin is required; pass --site-url https://blog.example.com." >&2
    exit 2
}
case "$PORT" in
    ''|*[!0-9]*) printf '%s\n' "Port must be a number between 1024 and 65535." >&2; exit 2 ;;
esac
[ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || {
    printf '%s\n' "Port must be a number between 1024 and 65535." >&2
    exit 2
}

SITE_HOSTNAME=$("$PYTHON_BINARY" -c 'import sys; from urllib.parse import urlsplit; value=urlsplit(sys.argv[1]); valid=(value.scheme == "https" and bool(value.hostname) and value.port in (None, 443) and not value.username and not value.password and not value.query and not value.fragment and value.path in ("", "/")); raise SystemExit(0 if valid else 2);' "$SITE_URL" && "$PYTHON_BINARY" -c 'import sys; from urllib.parse import urlsplit; print(urlsplit(sys.argv[1]).hostname)' "$SITE_URL") || {
    printf '%s\n' "--site-url must be one HTTPS origin on port 443 without a path, query, fragment or credentials." >&2
    exit 2
}
SITE_AUTHORITY=$("$PYTHON_BINARY" -c 'import sys; from urllib.parse import urlsplit; print(urlsplit(sys.argv[1]).netloc)' "$SITE_URL")

if [ "$SOURCE_MODE" = "local" ]; then
    [ -f "$PROJECT_DIRECTORY/wsgi.py" ] && [ -f "$PROJECT_DIRECTORY/requirements.txt" ] || {
        printf '%s\n' "--local must be run from a complete baka blog checkout." >&2
        exit 1
    }
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    printf '%s\n' \
        "macOS deployment preflight passed." \
        "Python: $PYTHON_BINARY" \
        "Architecture: $(uname -m)" \
        "Project: $PROJECT_DIRECTORY" \
        "Instance: $INSTANCE_DIRECTORY" \
        "Origin: $SITE_URL" \
        "Loopback: 127.0.0.1:$PORT"
    exit 0
fi

if [ "$SOURCE_MODE" = "remote" ]; then
    mkdir -p "$(dirname "$PROJECT_DIRECTORY")"
    if [ -d "$PROJECT_DIRECTORY/.git" ]; then
        if [ -n "$(git -C "$PROJECT_DIRECTORY" status --porcelain --untracked-files=normal)" ]; then
            printf '%s\n' "The deployment checkout has local changes; refusing to overwrite them." >&2
            exit 1
        fi
        git -C "$PROJECT_DIRECTORY" fetch --prune origin "$BRANCH"
        git -C "$PROJECT_DIRECTORY" checkout "$BRANCH"
        git -C "$PROJECT_DIRECTORY" merge --ff-only "origin/$BRANCH"
    elif [ -e "$PROJECT_DIRECTORY" ]; then
        if [ -n "$(find "$PROJECT_DIRECTORY" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
            printf 'Project directory exists and is not an empty Git checkout: %s\n' "$PROJECT_DIRECTORY" >&2
            exit 1
        fi
        git clone --branch "$BRANCH" --single-branch "$REPOSITORY_URL" "$PROJECT_DIRECTORY"
    else
        git clone --branch "$BRANCH" --single-branch "$REPOSITORY_URL" "$PROJECT_DIRECTORY"
    fi
fi

for required_file in wsgi.py requirements.txt scripts/macos-run.sh; do
    [ -f "$PROJECT_DIRECTORY/$required_file" ] || {
        printf 'Deployment checkout is missing: %s\n' "$required_file" >&2
        exit 1
    }
done

VENV_DIRECTORY="$PROJECT_DIRECTORY/.venv-macos"
if [ ! -x "$VENV_DIRECTORY/bin/python" ]; then
    "$PYTHON_BINARY" -m venv "$VENV_DIRECTORY"
fi
VENV_PYTHON="$VENV_DIRECTORY/bin/python"
"$VENV_PYTHON" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] < (3, 15)))'

if [ "$OFFLINE" -eq 1 ]; then
    "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-index \
        --find-links "$PROJECT_DIRECTORY/wheelhouse" \
        -r "$PROJECT_DIRECTORY/requirements.txt"
else
    "$VENV_PYTHON" -m pip install --disable-pip-version-check \
        -r "$PROJECT_DIRECTORY/requirements.txt"
fi
"$VENV_PYTHON" -m pip check

mkdir -p "$INSTANCE_DIRECTORY/data" "$INSTANCE_DIRECTORY/uploads" \
    "$INSTANCE_DIRECTORY/cache" "$INSTANCE_DIRECTORY/logs" \
    "$INSTANCE_DIRECTORY/backups" "$INSTANCE_DIRECTORY/tmp" \
    "$(dirname "$CONFIG_FILE")" "$(dirname "$PLIST_FILE")" "$LOG_DIRECTORY"
chmod 700 "$APP_SUPPORT_DIRECTORY" "$INSTANCE_DIRECTORY" "$(dirname "$CONFIG_FILE")" "$LOG_DIRECTORY"

SECRET_KEY=$(read_config_value CLOUD_DIARY_SECRET_KEY)
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$("$PYTHON_BINARY" -c 'import secrets; print(secrets.token_hex(32))')
fi
if [ "${#SECRET_KEY}" -lt 32 ]; then
    printf '%s\n' "Existing production secret is too short; replace the configuration securely." >&2
    exit 1
fi

CONFIG_TEMP="${CONFIG_FILE}.new.$$"
umask 077
{
    printf 'CLOUD_DIARY_ENV=production\n'
    printf 'CLOUD_DIARY_SECRET_KEY=%s\n' "$SECRET_KEY"
    printf 'CLOUD_DIARY_SITE_URL=%s\n' "$SITE_URL"
    printf 'CLOUD_DIARY_INSTANCE_PATH=%s\n' "$INSTANCE_DIRECTORY"
    printf 'CLOUD_DIARY_TRUST_PROXY_HEADERS=1\n'
    printf 'CLOUD_DIARY_TEXT_COMPRESSION=0\n'
    printf 'CLOUD_DIARY_PROJECT_DIRECTORY=%s\n' "$PROJECT_DIRECTORY"
    printf 'PORT=%s\n' "$PORT"
    printf 'WORKERS=2\n'
    printf 'THREADS=4\n'
} > "$CONFIG_TEMP"
chmod 600 "$CONFIG_TEMP"
mv "$CONFIG_TEMP" "$CONFIG_FILE"

export CLOUD_DIARY_ENV=production
export CLOUD_DIARY_SECRET_KEY="$SECRET_KEY"
export CLOUD_DIARY_SITE_URL="$SITE_URL"
export CLOUD_DIARY_INSTANCE_PATH="$INSTANCE_DIRECTORY"
export CLOUD_DIARY_TRUST_PROXY_HEADERS=1
export CLOUD_DIARY_TEXT_COMPRESSION=0
export CLOUD_DIARY_PROJECT_DIRECTORY="$PROJECT_DIRECTORY"
export PORT="$PORT"
export WORKERS=2
export THREADS=4

DOMAIN="gui/$(id -u)"
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN/$LABEL"
fi

if ! "$PYTHON_BINARY" -c 'import socket, sys; sock=socket.socket(); sock.bind(("127.0.0.1", int(sys.argv[1]))); sock.close()' "$PORT"; then
    printf 'Loopback port %s is already in use; rerun with --port NUMBER.\n' "$PORT" >&2
    exit 1
fi

cd "$PROJECT_DIRECTORY"
if [ -n "$(find "$INSTANCE_DIRECTORY/data" -maxdepth 1 -type f -name '*.db' -print -quit 2>/dev/null)" ]; then
    "$VENV_PYTHON" -m flask --app wsgi:app site-backup
fi
"$VENV_PYTHON" -m flask --app wsgi:app db upgrade
"$VENV_PYTHON" -m flask --app wsgi:app configure-deployment-domain "$SITE_HOSTNAME"
"$VENV_PYTHON" -m flask --app wsgi:app system-check

export BAKABLOG_MACOS_LABEL=$LABEL
export BAKABLOG_MACOS_CONFIG=$CONFIG_FILE
export BAKABLOG_MACOS_PROJECT=$PROJECT_DIRECTORY
export BAKABLOG_MACOS_STDOUT="$LOG_DIRECTORY/gunicorn-access.log"
export BAKABLOG_MACOS_STDERR="$LOG_DIRECTORY/gunicorn-error.log"
export BAKABLOG_MACOS_PLIST=$PLIST_FILE
"$PYTHON_BINARY" -c 'import os, plistlib; payload={"Label":os.environ["BAKABLOG_MACOS_LABEL"],"ProgramArguments":["/bin/sh",os.path.join(os.environ["BAKABLOG_MACOS_PROJECT"],"scripts","macos-run.sh"),os.environ["BAKABLOG_MACOS_CONFIG"]],"WorkingDirectory":os.environ["BAKABLOG_MACOS_PROJECT"],"RunAtLoad":True,"KeepAlive":{"SuccessfulExit":False},"ThrottleInterval":10,"ProcessType":"Background","StandardOutPath":os.environ["BAKABLOG_MACOS_STDOUT"],"StandardErrorPath":os.environ["BAKABLOG_MACOS_STDERR"]}; target=os.environ["BAKABLOG_MACOS_PLIST"]; temporary=target+".new"; handle=open(temporary,"wb"); plistlib.dump(payload,handle,sort_keys=False); handle.close(); os.replace(temporary,target)'
chmod 600 "$PLIST_FILE"
plutil -lint "$PLIST_FILE" >/dev/null

if [ "$NO_START" -eq 1 ]; then
    printf '%s\n' \
        "macOS deployment installed and validated without starting." \
        "Start later with: $PROJECT_DIRECTORY/scripts/manage-macos.sh start"
    exit 0
fi

launchctl bootstrap "$DOMAIN" "$PLIST_FILE"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

attempt=0
while [ "$attempt" -lt 30 ]; do
    if curl --noproxy '*' --fail --silent --output /dev/null \
        --header "Host: $SITE_AUTHORITY" \
        --header "X-Forwarded-Host: $SITE_AUTHORITY" \
        --header "X-Forwarded-Proto: https" \
        "http://127.0.0.1:${PORT}/healthz"; then
        printf '%s\n' \
            "macOS deployment completed." \
            "LaunchAgent: $PLIST_FILE" \
            "Instance data: $INSTANCE_DIRECTORY" \
            "Logs: $LOG_DIRECTORY" \
            "Loopback: 127.0.0.1:$PORT" \
            "Public origin: $SITE_URL"
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done

printf '%s\n' "LaunchAgent did not pass its loopback health check." >&2
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
tail -n 80 "$LOG_DIRECTORY/gunicorn-error.log" 2>/dev/null || true
exit 1
