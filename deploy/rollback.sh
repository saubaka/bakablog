#!/usr/bin/env bash
# Put the previous release back by hand (the deploy does this by itself when its own checks fail; this is for "it passed the checks but I do not like it").
#
#   sudo bash /opt/bakablog/current/deploy/rollback.sh            # code (and its Python packages if they differed) go back; the data stays as it is
#   sudo bash /opt/bakablog/current/deploy/rollback.sh --data     # ALSO restore the newest pre-deploy backup: everything written since the deploy is lost
#
# Use --data only if the new release changed the database schema (look at the deploy output / `flask --app app init-db` revision) — an older release
# cannot read a newer schema. Without --data the site keeps whatever was posted since the deploy.
set -Eeuo pipefail
APP=${BB_APP:-/opt/bakablog}; DATA=${BB_DATA:-/var/lib/bakablog}; ENV_FILE=${BB_ENV_FILE:-/etc/bakablog/production.env}
SVC_USER=${BB_USER:-bakablog}; SERVICE=${BB_SERVICE:-bakablog}; PORT=${BB_PORT:-8080}; SYSTEMCTL=${BB_SYSTEMCTL:-systemctl}
SYSTEM_MODE=${BB_SYSTEM_MODE:-1}; PYTHON_WANT=${BB_PYTHON:-3.12}
CURRENT="$APP/current"; PREVIOUS="$APP/previous"; VENV="$APP/venv"
WITH_DATA=0; [ "${1:-}" = "--data" ] && WITH_DATA=1
die() { printf '\033[31m[rollback] %s\033[0m\n' "$*" >&2; exit 1; }
say() { printf '\033[1m[rollback]\033[0m %s\n' "$*"; }
if [ "$SYSTEM_MODE" = 1 ] && [ "$(id -u)" != 0 ]; then exec sudo -n bash "$0" "$@"; fi
[ -d "$PREVIOUS/backend/app" ] || die "there is no previous release in $PREVIOUS"
if command -v sha256sum >/dev/null 2>&1; then sha() { sha256sum "$1" | cut -d' ' -f1; }; else sha() { shasum -a 256 "$1" | cut -d' ' -f1; }; fi

as_app() { ( set -a; . "$ENV_FILE"; set +a; cd "$CURRENT/backend"; if [ "$SYSTEM_MODE" = 1 ]; then exec runuser -u "$SVC_USER" --preserve-environment -- "$@"; else exec "$@"; fi ); }

now="$(grep '^BUILD=' "$CURRENT/RELEASE" 2>/dev/null | cut -d= -f2 || true)"; back="$(grep '^BUILD=' "$PREVIOUS/RELEASE" | cut -d= -f2)"
say "going back from ${now:-?} to $back"
"$SYSTEMCTL" stop "$SERVICE"
rsync -rlt --delete "$PREVIOUS/" "$CURRENT/"
find "$CURRENT" -type d -exec chmod 750 {} +; find "$CURRENT" -type f -exec chmod 640 {} +
if [ "$SYSTEM_MODE" = 1 ]; then chown -R "root:$SVC_USER" "$CURRENT"; fi
want="$(sha "$CURRENT/backend/requirements.txt")"
target="$APP/venvs/${want:0:16}"
if [ "$(readlink "$VENV" 2>/dev/null || true)" != "$target" ]; then
  if [ ! -f "$target/.complete" ]; then
    say "the previous release pinned other packages and their environment is gone: rebuilding it"
    command -v uv >/dev/null || die "uv is not installed (it is installed by the deploy script)"
    mkdir -p "$APP/venvs"; rm -rf "$target"
    UV_PYTHON_INSTALL_DIR="$APP/python" uv venv --quiet --python "$PYTHON_WANT" "$target"
    UV_PYTHON_INSTALL_DIR="$APP/python" uv pip install --quiet --compile-bytecode --python "$target/bin/python" -r "$CURRENT/backend/requirements.txt"
    : > "$target/.complete"
    if [ "$SYSTEM_MODE" = 1 ]; then chown -R "root:$SVC_USER" "$APP/venvs"; chmod -R g+rX,o-rwx "$APP/venvs"; fi
  fi
  ln -sfn "$target" "$VENV"
fi
if [ "$WITH_DATA" = 1 ]; then
  backup="$(ls -1t "$DATA"/backups/backup-*-pre-deploy.tar.gz 2>/dev/null | head -1 || true)"
  [ -n "$backup" ] || die "no pre-deploy backup in $DATA/backups"
  say "restoring the data from $(basename "$backup") (the current data is kept first as a pre-restore backup)"
  as_app "$VENV/bin/flask" --app app restore "$backup" --yes
fi
"$SYSTEMCTL" start "$SERVICE"
for i in $(seq 1 45); do curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$PORT/api/health" && { say "OK: $back is running again"; exit 0; }; sleep 1; done
die "the service did not answer; look at: journalctl -u $SERVICE -n 100"
