#!/bin/sh
set -eu

SCRIPT_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIRECTORY="$SCRIPT_DIRECTORY/.venv-macos"
INSTANCE_DIRECTORY="$SCRIPT_DIRECTORY/instance"
HOST="127.0.0.1"
PORT="5010"
PYTHON_REQUESTED=""
OFFLINE=0
CHECK_ONLY=0

usage() {
    printf '%s\n' \
        "Usage: ./start-macos.sh [options]" \
        "" \
        "  --python PATH       Python 3.11-3.14 executable" \
        "  --instance-dir PATH Local instance directory (default: ./instance)" \
        "  --port NUMBER       Preferred loopback port (default: 5010; auto-switches if busy)" \
        "  --offline           Install only from wheelhouse" \
        "  --check-only        Migrate and validate without starting Flask" \
        "  --help              Show this help"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --python)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --python." >&2; exit 2; }
            PYTHON_REQUESTED=$2
            shift 2
            ;;
        --instance-dir)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --instance-dir." >&2; exit 2; }
            INSTANCE_DIRECTORY=$2
            shift 2
            ;;
        --port)
            [ "$#" -ge 2 ] || { printf '%s\n' "Missing value for --port." >&2; exit 2; }
            PORT=$2
            shift 2
            ;;
        --offline)
            OFFLINE=1
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
    printf '%s\n' "This launcher only supports macOS." >&2
    exit 1
}

case "$PORT" in
    ''|*[!0-9]*) printf '%s\n' "Port must be a number between 1024 and 65535." >&2; exit 2 ;;
esac
[ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || {
    printf '%s\n' "Port must be a number between 1024 and 65535." >&2
    exit 2
}

case "$INSTANCE_DIRECTORY" in
    /*) ;;
    *) INSTANCE_DIRECTORY="$SCRIPT_DIRECTORY/$INSTANCE_DIRECTORY" ;;
esac

find_python() {
    if [ -n "$PYTHON_REQUESTED" ]; then
        candidates=$PYTHON_REQUESTED
    else
        # Reuse an already-created project environment before checking the
        # system PATH. This keeps local startup working when macOS only has
        # its system Python 3.9, while the project venv already has 3.11+.
        if [ -x "$VENV_DIRECTORY/bin/python" ] && \
            "$VENV_DIRECTORY/bin/python" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] < (3, 15)))' 2>/dev/null; then
            printf '%s\n' "$VENV_DIRECTORY/bin/python"
            return 0
        fi
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

if [ ! -x "$VENV_DIRECTORY/bin/python" ]; then
    "$PYTHON_BINARY" -m venv "$VENV_DIRECTORY"
fi
VENV_PYTHON="$VENV_DIRECTORY/bin/python"
"$VENV_PYTHON" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] < (3, 15)))'

if [ "$OFFLINE" -eq 1 ]; then
    "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-index \
        --find-links "$SCRIPT_DIRECTORY/wheelhouse" \
        -r "$SCRIPT_DIRECTORY/requirements.txt"
else
    "$VENV_PYTHON" -m pip install --disable-pip-version-check \
        -r "$SCRIPT_DIRECTORY/requirements.txt"
fi

port_owner() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN -F c 2>/dev/null | sed -n 's/^c//p' | head -1
}

port_is_free() {
    [ -z "$(port_owner "$1")" ]
}

if [ "$CHECK_ONLY" -eq 0 ] && ! port_is_free "$PORT"; then
    ORIGINAL_PORT=$PORT
    printf '端口 %s 已被占用（进程：%s）。\n' "$PORT" "$(port_owner "$PORT")" >&2
    LAST_PORT=$((PORT + 20))
    [ "$LAST_PORT" -le 65535 ] || LAST_PORT=65535
    CANDIDATE=$((PORT + 1))
    while [ "$CANDIDATE" -le "$LAST_PORT" ]; do
        if port_is_free "$CANDIDATE"; then
            PORT=$CANDIDATE
            break
        fi
        CANDIDATE=$((CANDIDATE + 1))
    done
    [ "$PORT" -ne "$ORIGINAL_PORT" ] || {
        printf '从 %s 起没有可用端口；请用 --port 指定其他端口。\n' "$ORIGINAL_PORT" >&2
        exit 1
    }
    printf '本次改用空闲端口 %s，请按启动输出中的实际地址访问。\n' "$PORT" >&2
fi

export CLOUD_DIARY_ENV=development
export CLOUD_DIARY_SITE_URL="http://${HOST}:${PORT}"
export CLOUD_DIARY_INSTANCE_PATH="$INSTANCE_DIRECTORY"
export CLOUD_DIARY_TRUST_PROXY_HEADERS=0

cd "$SCRIPT_DIRECTORY"
"$VENV_PYTHON" -m flask --app wsgi:app db upgrade
"$VENV_PYTHON" -m flask --app wsgi:app system-check

if [ "$CHECK_ONLY" -eq 1 ]; then
    printf 'macOS local validation passed: %s\n' "$CLOUD_DIARY_SITE_URL"
    exit 0
fi

printf 'Starting baka blog at %s\n' "$CLOUD_DIARY_SITE_URL"
printf '首次使用请打开该地址，按页面向导创建管理员；按 Ctrl+C 停止。\n'
exec "$VENV_PYTHON" -m flask --app wsgi:app run --host "$HOST" --port "$PORT" \
    --no-debugger --no-reload
