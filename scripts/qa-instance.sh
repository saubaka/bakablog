#!/usr/bin/env bash
# The separate instance the admin browser checks run against (never your real data): its own data folder, demo content, and an
# administrator with a random password kept in backend/data-qa/credentials.json (0600, git-ignored; nothing is printed).
#
#   scripts/qa-instance.sh start      create it if missing, then run gunicorn on 127.0.0.1:5310 in the background
#   scripts/qa-instance.sh stop
#   scripts/qa-instance.sh reset      stop and delete it (the next start makes a fresh one)
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
DATA="$BACKEND/data-qa"
PORT="${BB_QA_PORT:-5310}"
PIDFILE="$DATA/gunicorn.pid"
export BLOG_DATA_DIR="$DATA"

case "${1:-}" in
  start)
    if [ ! -f "$DATA/credentials.json" ]; then
      rm -rf "$DATA"; mkdir -p "$DATA"; chmod 700 "$DATA"
      user="qa-admin"
      pass="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
      # the credentials file is written only after the administrator really exists, so a failed first start leaves nothing half-made behind
      ( cd "$BACKEND" && .venv/bin/flask --app app seed-demo --owner "$user" --password "$pass" > "$DATA/seed.log" 2>&1 ) || { cat "$DATA/seed.log" >&2; rm -rf "$DATA"; echo "could not create the QA instance" >&2; exit 1; }
      rm -f "$DATA/seed.log"                       # it contains the throw-away one-time setup token the app logs on a first run
      ( umask 077; printf '{"username": "%s", "password": "%s"}\n' "$user" "$pass" > "$DATA/credentials.json" )
      echo "created the QA instance (credentials in $DATA/credentials.json)"
    fi
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then echo "already running on :$PORT"; exit 0; fi
    ( cd "$BACKEND" && nohup .venv/bin/gunicorn -w 1 --threads 4 --keep-alive 5 -b "127.0.0.1:$PORT" --pid "$PIDFILE" wsgi:app > "$DATA/gunicorn.log" 2>&1 & )
    for _ in $(seq 1 40); do curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/health" 2>/dev/null && { echo "QA instance on http://127.0.0.1:$PORT"; exit 0; }; sleep 0.5; done
    echo "it did not come up: see $DATA/gunicorn.log" >&2; exit 1 ;;
  stop)
    if [ -f "$PIDFILE" ]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; echo stopped; else echo "not running"; fi ;;
  reset)
    "$0" stop || true
    rm -rf "$DATA"; echo "removed $DATA" ;;
  *) echo "usage: $0 start|stop|reset" >&2; exit 2 ;;
esac
