#!/usr/bin/env bash
# Prove that a backup can really be restored — without touching the live site.
#
#   deploy/restore-drill.sh [BACKUP_FILE]      # on the server (as root or the service account); default: the newest backup, or a fresh one if there is none
#
# It restores the backup into a scratch copy of the data folder with the real `flask restore` (so the same checks and the same code path as a
# disaster recovery run), then compares what came back with what the backup's manifest promised: row counts, picture files, database integrity.
# A backup nobody has restored is a hope, not a backup — do this after every change to the backup code and now and then on the real data.
set -Eeuo pipefail
APP=${BB_APP:-/opt/bakablog}
DATA=${BB_DATA:-/var/lib/bakablog}
ENV_FILE=${BB_ENV_FILE:-/etc/bakablog/production.env}
SVC_USER=${BB_USER:-bakablog}
SYSTEM_MODE=${BB_SYSTEM_MODE:-1}
VENV="$APP/venv"; CURRENT="$APP/current"
die() { printf '\033[31m[drill] %s\033[0m\n' "$*" >&2; exit 1; }
say() { printf '[drill] %s\n' "$*"; }
[ -f "$ENV_FILE" ] || die "no $ENV_FILE"
[ -x "$VENV/bin/flask" ] || die "no application in $APP"

# as_app CMD…: the service account (when root on the server), the production environment, the installed backend folder
as_app() {
  ( set -a; . "$ENV_FILE"; set +a; cd "$CURRENT/backend"
    if [ "$SYSTEM_MODE" = 1 ] && [ "$(id -u)" = 0 ]; then exec runuser -u "$SVC_USER" --preserve-environment -- "$@"; else exec "$@"; fi )
}
live_flask() { as_app "$VENV/bin/flask" --app app "$@"; }

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ]; then
  ARCHIVE="$(ls -1t "$DATA"/backups/backup-*.tar.gz 2>/dev/null | head -1 || true)"
  if [ -z "$ARCHIVE" ]; then say "no backup yet: making one"; name="$(live_flask backup --label drill | awk '{print $1}')"; ARCHIVE="$DATA/backups/$name"; fi
fi
[ -f "$ARCHIVE" ] || die "no such backup: $ARCHIVE"
say "backup: $(basename "$ARCHIVE") ($(du -h "$ARCHIVE" | cut -f1))"

SCRATCH="$(mktemp -d "$DATA/.drill.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
if [ "$SYSTEM_MODE" = 1 ] && [ "$(id -u)" = 0 ]; then chown "$SVC_USER" "$SCRATCH"; fi
scratch_flask() {   # the same application and environment, but pointed at the scratch folder
  as_app env BLOG_DATA_DIR="$SCRATCH" BLOG_DB_PATH="$SCRATCH/blog.sqlite" "$VENV/bin/flask" --app app "$@"
}
say "preparing an empty site in the scratch folder"
scratch_flask init-db > /dev/null
say "restoring (the real procedure: checksum, integrity, schema check, safety backup, copy back, media swap)"
scratch_flask restore "$ARCHIVE" --yes

say "comparing with the manifest"
as_app env BLOG_DATA_DIR="$SCRATCH" "$VENV/bin/python" - "$ARCHIVE" "$SCRATCH" <<'PY'
import json, sqlite3, sys, tarfile
from pathlib import Path

archive, scratch = sys.argv[1], Path(sys.argv[2])
with tarfile.open(archive, "r:gz") as tar:
    manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
con = sqlite3.connect(f"file:{scratch / 'blog.sqlite'}?mode=ro", uri=True)
problems = []
def check(label, expected, got):
    ok = expected == got
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: expected {expected}, got {got}")
    if not ok:
        problems.append(label)
tables = {"posts": "posts", "moments": "moments", "pages": "pages", "media": "media", "admins": "admin_users"}
for key, table in tables.items():
    check(f"rows in {table}", manifest["counts"][key], con.execute(f"select count(*) from {table}").fetchone()[0])
check("picture files", manifest["media_files"], sum(1 for _ in (scratch / "media").rglob("*.webp")))
check("integrity_check", "ok", con.execute("pragma integrity_check").fetchone()[0])
check("foreign_key_check (rows with a broken reference)", 0, len(con.execute("pragma foreign_key_check").fetchall()))
check("schema revision", manifest["schema_revision"], con.execute("select version_num from alembic_version").fetchone()[0])
sys.exit(1 if problems else 0)
PY
say "the backup restores and matches its manifest. The live data was not touched; the scratch folder is removed."
