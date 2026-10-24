#!/usr/bin/env bash
# Runs ON THE SERVER as root (deploy.sh uploads it with the release and starts it):   remote-update.sh /path/to/release.tar.gz
# Installs a release, or — the first time — also prepares the machine (account, folders, Python, units). Idempotent.
#
#   1. unpack to a staging folder, clean macOS junk (._* files break alembic), read RELEASE
#   2. prepare: account, folders, env file (created once, never overwritten), Python packages into venv.new (the running site is untouched)
#   3. back up code and data (the app's own online backup, labelled pre-deploy), remember the database revision
#   4. stop the site, swap the code in, migrate, run the self-check, start, check the public pages and the build id
#   5. ANY failure after the stop: put the previous code back; if the schema changed also put the pre-deploy backup back; start; say so; exit 1
#
# Exit codes are never masked: no `cmd | tail`, no `|| true` on anything that matters (and the rollback does not depend on `set -e` / ERR traps).
# Paths and commands can be overridden for the rehearsal (deploy/rehearse.sh): BB_APP BB_DATA BB_ENV_FILE BB_USER BB_SERVICE BB_PORT BB_SYSTEMCTL BB_SYSTEM_MODE.
set -Eeuo pipefail
umask 027

APP=${BB_APP:-/opt/bakablog}
DATA=${BB_DATA:-/var/lib/bakablog}
ENV_FILE=${BB_ENV_FILE:-/etc/bakablog/production.env}
SVC_USER=${BB_USER:-bakablog}
SERVICE=${BB_SERVICE:-bakablog}
PORT=${BB_PORT:-8080}
SYSTEMCTL=${BB_SYSTEMCTL:-systemctl}
SYSTEM_MODE=${BB_SYSTEM_MODE:-1}               # 0 = rehearsal: no account, no chown, no systemd units
PYTHON_WANT=${BB_PYTHON:-3.12}
UV_VERSION=${BB_UV_VERSION:-0.12.17}
KEEP_PREDEPLOY=${BB_KEEP_PREDEPLOY:-5}

CURRENT="$APP/current"
PREVIOUS="$APP/previous"
VENV="$APP/venv"                               # a symlink to one of $APP/venvs/<hash>: a Python environment cannot be moved (its scripts name their own path), so it is built where it stays
VENVS="$APP/venvs"
TARBALL=${1:-}

log()  { printf '\033[1m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[deploy] %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31m[deploy] %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$TARBALL" ] && [ -f "$TARBALL" ] || die "usage: remote-update.sh /path/to/release.tar.gz"
if [ "$SYSTEM_MODE" = 1 ] && [ "$(id -u)" != 0 ]; then exec sudo -n bash "$0" "$@"; fi
for tool in rsync curl tar python3 awk; do command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed (apt install rsync curl tar python3 gawk)"; done
if [ "$SYSTEM_MODE" = 1 ]; then for tool in systemctl runuser; do command -v "$tool" >/dev/null 2>&1 || die "$tool is missing"; done; fi
if command -v sha256sum >/dev/null 2>&1; then sha256() { sha256sum "$1" | cut -d' ' -f1; }; else sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }; fi
# the installed tree: directories 750, files 640, owned by root with the service group (plain chmod/chown: same on every rsync, GNU or BSD)
fix_perms() {
  find "$1" -type d -exec chmod 750 {} +
  find "$1" -type f -exec chmod 640 {} +
  if [ "$SYSTEM_MODE" = 1 ]; then chown -R "root:$SVC_USER" "$1"; fi
}

STAGE=""
VENV_SWITCHED=0
PREV_VENV_TARGET=""
NEW_VENV_DIR=""
SERVICE_STOPPED=0
PRE_BACKUP=""
PRE_REV=""
MIGRATION_STARTED=0
cleanup() { if [ -n "$STAGE" ]; then rm -rf "$STAGE"; fi; rm -f "$TARBALL"; }

# ---- helpers ------------------------------------------------------------------------------------------------------------------------
svc() { "$SYSTEMCTL" "$@"; }

# as_app CMD...: the service account, the production environment, the CURRENT release's backend folder
as_app() {
  (
    set -a; . "$ENV_FILE"; set +a
    cd "$CURRENT/backend"
    if [ "$SYSTEM_MODE" = 1 ]; then exec runuser -u "$SVC_USER" --preserve-environment -- "$@"; else exec "$@"; fi
  )
}
flask_app() { as_app "$VENV/bin/flask" --app app "$@"; }

env_value() { ( set -a; . "$ENV_FILE"; set +a; eval "printf '%s' \"\${$1:-}\"" ); }

db_revision() {
  local db; db="$(env_value BLOG_DB_PATH)"; [ -n "$db" ] || db="$(env_value BLOG_DATA_DIR)/blog.sqlite"; [ -f "$db" ] || { printf ''; return 0; }
  "$VENV/bin/python" - "$db" <<'PY'
import sqlite3, sys
try:
    con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    row = con.execute("select version_num from alembic_version").fetchone()
    print(row[0] if row else "", end="")
except Exception:
    print("", end="")
PY
}

http() {   # http PATH [curl options]: GET from the local service the way the proxy would
  local path="$1"; shift
  curl -fsS --max-time 10 -H 'X-Forwarded-Proto: https' -H "Host: $SITE_HOST" "$@" "http://127.0.0.1:$PORT$path"
}

wait_healthy() {
  local i
  for i in $(seq 1 45); do
    if http /api/health -o /dev/null 2>/dev/null; then return 0; fi
    sleep 1
  done
  return 1
}

# ---- 1. unpack ----------------------------------------------------------------------------------------------------------------------
mkdir -p "$APP"
STAGE="$(mktemp -d "$APP/.stage.XXXXXX")"
trap cleanup EXIT
tar -xzf "$TARBALL" -C "$STAGE"
find "$STAGE" -name '._*' -delete                       # macOS AppleDouble files: alembic imports every *.py it finds
find "$STAGE" -name '.DS_Store' -delete
[ -f "$STAGE/RELEASE" ] || die "the archive has no RELEASE file"
# shellcheck disable=SC1091
. "$STAGE/RELEASE"                                       # VERSION=… BUILD=… CREATED=…
log "release $VERSION (build $BUILD, made $CREATED)"
for f in backend/app backend/migrations backend/wsgi.py backend/requirements.txt frontend/dist/public.html frontend/dist/admin.html frontend/dist/preview.html deploy/bakablog.service; do
  [ -e "$STAGE/$f" ] || die "the archive is incomplete: $f is missing"
done

# ---- 2. prepare the machine (first time) and the new Python environment ---------------------------------------------------------------
if [ "$SYSTEM_MODE" = 1 ]; then
  getent group "$SVC_USER" >/dev/null || groupadd --system "$SVC_USER"
  id "$SVC_USER" >/dev/null 2>&1 || useradd --system --gid "$SVC_USER" --home-dir "$DATA" --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$DATA" "$DATA/backups"
  install -d -o root -g "$SVC_USER" -m 0750 "$APP"
  install -d -o root -g root -m 0755 "$(dirname "$ENV_FILE")"
else
  mkdir -p "$DATA" "$DATA/backups" "$(dirname "$ENV_FILE")"
fi

if [ ! -f "$ENV_FILE" ]; then
  secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  ( umask 077; sed -e "s|__GENERATE_ME__|$secret|" -e "s|__GENERATE_TOKEN__|$token|" "$STAGE/deploy/production.env.example" > "$ENV_FILE" )
  chmod 0600 "$ENV_FILE"
  die "created $ENV_FILE with a fresh secret and a one-time setup token (read it there; it is not printed here). Edit BLOG_SITE_URL (and look at the rest), then run the deploy again."
fi
if grep -qE '^BLOG_SITE_URL=https://blog\.example\.com/?$|__GENERATE_' "$ENV_FILE"; then
  die "$ENV_FILE still has the example BLOG_SITE_URL or secret: edit it first."
fi
SITE_HOST="$(env_value BLOG_SITE_URL)"; SITE_HOST="${SITE_HOST#*://}"; SITE_HOST="${SITE_HOST%%/*}"
[ -n "$SITE_HOST" ] || die "BLOG_SITE_URL is empty in $ENV_FILE"

install_uv() {
  command -v uv >/dev/null 2>&1 && return 0
  log "installing uv $UV_VERSION (Python package and interpreter manager)"
  python3 -m venv "$APP/tools"
  "$APP/tools/bin/pip" install --quiet "uv==$UV_VERSION"
  ln -sf "$APP/tools/bin/uv" /usr/local/bin/uv
}

want_hash="$(sha256 "$STAGE/backend/requirements.txt")"
short_hash="${want_hash:0:16}"
NEW_VENV_DIR="$VENVS/$short_hash"
if [ ! -f "$NEW_VENV_DIR/.complete" ] || ! "$NEW_VENV_DIR/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  install_uv
  log "building the Python environment ($(wc -l < "$STAGE/backend/requirements.txt" | tr -d ' ') lines of pins) beside the running one"
  mkdir -p "$VENVS"
  rm -rf "$NEW_VENV_DIR"                                  # a half-built one from an earlier attempt
  UV_PYTHON_INSTALL_DIR="$APP/python" uv venv --quiet --python "$PYTHON_WANT" "$NEW_VENV_DIR"
  UV_PYTHON_INSTALL_DIR="$APP/python" uv pip install --quiet --compile-bytecode --python "$NEW_VENV_DIR/bin/python" -r "$STAGE/backend/requirements.txt"
  : > "$NEW_VENV_DIR/.complete"
else
  log "the Python environment for these pins already exists ($short_hash)"
fi
# Compiled bytecode must exist before the service account runs anything: the units set PYTHONDONTWRITEBYTECODE and the tree is read-only for them, so
# without it every start (the maintenance job starts every few minutes) would compile the whole framework from source (seconds of CPU each time).
"$NEW_VENV_DIR/bin/python" -m compileall -q -j 0 "$NEW_VENV_DIR/lib" >/dev/null 2>&1 || warn "could not precompile the packages (the site still works, starts are slower)"
# the new code must at least import with its packages (this does not touch the site)
(
  set -a; . "$ENV_FILE"; set +a
  cd "$STAGE/backend"
  "$NEW_VENV_DIR/bin/python" -c 'import app; print("import ok")' >/dev/null
) || die "the new code does not import with its packages; nothing was changed"

if [ "$SYSTEM_MODE" = 1 ]; then
  for unit in bakablog.service bakablog-maintenance.service bakablog-maintenance.timer; do
    if ! cmp -s "$STAGE/deploy/$unit" "/etc/systemd/system/$unit"; then install -m 0644 "$STAGE/deploy/$unit" "/etc/systemd/system/$unit"; UNITS_CHANGED=1; fi
  done
  [ "${UNITS_CHANGED:-0}" = 1 ] && svc daemon-reload
fi

# ---- 3. back up -----------------------------------------------------------------------------------------------------------------------
if [ -d "$CURRENT/backend/app" ] && [ -x "$VENV/bin/python" ]; then
  PRE_REV="$(db_revision)"
  if [ -n "$PRE_REV" ]; then
    log "backing up the data with the running release's own backup (schema $PRE_REV)"
    PRE_BACKUP="$(flask_app backup --label pre-deploy | awk '{print $1}')"
    [ -n "$PRE_BACKUP" ] && [ -f "$DATA/backups/$PRE_BACKUP" ] || die "the pre-deploy backup was not written; nothing was changed"
    log "backup: $PRE_BACKUP ($(du -h "$DATA/backups/$PRE_BACKUP" | cut -f1))"
  fi
  rm -rf "$PREVIOUS"
  cp -a "$CURRENT" "$PREVIOUS"
else
  log "first installation: nothing to back up"
fi

# ---- rollback ----------------------------------------------------------------------------------------------------------------------
rollback() {
  trap - ERR
  set +e
  local why="$1"
  warn "FAILED: $why"
  warn "rolling back"
  svc stop "$SERVICE" || die "cannot stop $SERVICE for rollback; code and data were left in place; stop it before manual recovery"
  if [ -d "$PREVIOUS/backend/app" ]; then
    rsync -rlt --delete "$PREVIOUS/" "$CURRENT/" && fix_perms "$CURRENT"
    if [ "$VENV_SWITCHED" = 1 ] && [ -n "$PREV_VENV_TARGET" ]; then ln -sfn "$PREV_VENV_TARGET" "$VENV"; fi
    # a migration that started may have changed the schema even if it did not finish: the data goes back to the moment before the deploy
    # (the site was stopped, so nothing newer exists; the failed state is kept by the restore's own pre-restore backup)
    if [ "$MIGRATION_STARTED" = 1 ] && [ -n "$PRE_BACKUP" ]; then
      warn "restoring the pre-deploy backup $PRE_BACKUP (schema was $PRE_REV, is now $(db_revision))"
      flask_app restore "$DATA/backups/$PRE_BACKUP" --yes || warn "RESTORE FAILED: the backup is in $DATA/backups/$PRE_BACKUP; restore it by hand with: flask --app app restore <file> --yes"
    fi
    svc start "$SERVICE" || true
    if wait_healthy; then warn "the previous release is running again."; else warn "the previous release did not come up either: look at 'journalctl -u $SERVICE -n 100'"; fi
  else
    warn "there is no previous release (first installation): the service stays stopped. Look at 'journalctl -u $SERVICE -n 100'."
  fi
  exit 1
}

# ---- 4. swap and start ------------------------------------------------------------------------------------------------------------------
# From here on every step must succeed or the rollback runs. This is written out step by step (`must`) and does NOT lean on `set -e` or an ERR trap:
# bash 3.2 (macOS, used in the rehearsal) and bash 5 disagree about running an ERR trap for a failure inside a function.
set +e
trap - ERR
must() { "$@" || rollback "'$*' failed"; }

log "stopping $SERVICE"
svc stop "$SERVICE" || die "cannot stop $SERVICE; update aborted before switching code, environment or database"
SERVICE_STOPPED=1

PREV_VENV_TARGET="$(readlink "$VENV" 2>/dev/null)"
if [ "$PREV_VENV_TARGET" != "$NEW_VENV_DIR" ]; then
  must ln -sfn "$NEW_VENV_DIR" "$VENV"
  VENV_SWITCHED=1
fi
must mkdir -p "$CURRENT"
echo "$BUILD" > "$STAGE/backend/BUILD" || rollback "cannot write the build id"
must rsync -rlt --delete "$STAGE/" "$CURRENT/"
"$NEW_VENV_DIR/bin/python" -m compileall -q -j 0 "$CURRENT/backend/app" "$CURRENT/backend/migrations" >/dev/null 2>&1 || warn "could not precompile the application"
must fix_perms "$CURRENT"
if [ "$SYSTEM_MODE" = 1 ]; then
  chown -R "root:$SVC_USER" "$VENVS" "$APP/python" 2>/dev/null
  chmod -R g+rX,o-rwx "$VENVS" "$APP/python" 2>/dev/null
fi
find "$CURRENT" -name '._*' -delete

log "migrating the database"
MIGRATION_STARTED=1
must flask_app init-db
log "self-check"
must flask_app doctor

log "starting $SERVICE"
must svc start "$SERVICE"
wait_healthy || rollback "the service did not answer /api/health within 45 s"

# ---- check what a visitor would get --------------------------------------------------------------------------------------------------
health="$(http /api/health)" || rollback "GET /api/health failed"
running="$(printf '%s' "$health" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("version","")+" "+d.get("build",""))')" || rollback "/api/health is not JSON: $health"
[ "$running" = "$VERSION $BUILD" ] || rollback "the running service reports '$running', expected '$VERSION $BUILD' (an old process still answering?)"
for path in / /blog /moments /archive /feed/posts.xml /sitemap.xml /robots.txt /api/site /admin/ /admin/preview-frame; do
  code="$(http "$path" -o /dev/null -w '%{http_code}')"
  [ "$code" = 200 ] || rollback "GET $path answered ${code:-nothing}"
done
home="$(http /)" || rollback "GET / failed"
case "$home" in *'id="app"'*) ;; *) rollback "the home page has no #app (the front end shell is wrong)";; esac
case "$home" in *'<!--bb:'*) rollback "the home page still contains an unfilled <!--bb:…--> marker";; esac
http /admin/ | grep -q '/assets/' || rollback "the admin shell does not reference its assets"
http / -D - -o /dev/null | grep -qi '^content-security-policy:' || rollback "the home page carries no Content-Security-Policy"

# ---- 5. done ----------------------------------------------------------------------------------------------------------------------------
if [ "$SYSTEM_MODE" = 1 ]; then
  svc enable "$SERVICE" bakablog-maintenance.timer >/dev/null 2>&1 || warn "could not enable the service / timer at boot: run systemctl enable $SERVICE bakablog-maintenance.timer"
  svc start bakablog-maintenance.timer || warn "could not start the maintenance timer"
fi
ls -1t "$DATA/backups"/backup-*-pre-deploy.tar.gz 2>/dev/null | tail -n +"$((KEEP_PREDEPLOY + 1))" | while read -r old; do rm -f "$old"; done
# keep the environment in use and the one it replaced (a rollback needs it); older ones go
for d in "$VENVS"/*/; do
  d="${d%/}"; [ -d "$d" ] || continue
  if [ "$d" != "$NEW_VENV_DIR" ] && [ "$d" != "$PREV_VENV_TARGET" ]; then rm -rf "$d"; fi
done
log "OK: $VERSION (build $BUILD) is running${PRE_BACKUP:+; the way back is $PRE_BACKUP and $PREVIOUS}"
