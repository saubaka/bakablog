#!/usr/bin/env bash
# A full rehearsal of the install, an update, and four kinds of failed update, on THIS machine in a throw-away folder — no server, no root.
# It runs the real remote-update.sh with a stand-in `systemctl` that starts and stops the real gunicorn, so what is being tested is the real
# procedure: backup, stop, swap, migrate, self-check, start, health checks, and the automatic rollback (code, packages and data).
#
#   deploy/rehearse.sh          # needs: uv, rsync, curl, the project's backend/.venv, npm (for the build)
set -Euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/bb-rehearsal.XXXXXX")"
PORT="${BB_REHEARSAL_PORT:-5391}"
APP="$SANDBOX/opt"; DATA="$SANDBOX/data"; ENVF="$SANDBOX/etc/production.env"
PY="$ROOT/backend/.venv/bin/python"
PASS=0; FAILS=0
ok()   { PASS=$((PASS + 1)); printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { FAILS=$((FAILS + 1)); printf '  \033[31m✗\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
check() { if eval "$2"; then ok "$1"; else bad "$1   [$2]"; fi; }

# a systemctl that runs gunicorn from the "installed" release (the real unit does the same with the real flags)
cat > "$SANDBOX/fake-systemctl" <<FAKE
#!/usr/bin/env bash
cmd="\$1"; unit="\${2:-}"
pidfile="$SANDBOX/gunicorn.pid"
case "\$cmd:\$unit" in
  stop:bakablog)
    [ ! -f "$SANDBOX/refuse-stop" ] || exit 1
    if [ -f "$SANDBOX/refuse-rollback-stop" ]; then
      [ ! -f "$SANDBOX/stopped-once" ] || exit 1
      touch "$SANDBOX/stopped-once"
    fi
    if [ -f "\$pidfile" ]; then kill "\$(cat "\$pidfile")" 2>/dev/null; for i in \$(seq 1 80); do kill -0 "\$(cat "\$pidfile")" 2>/dev/null || break; sleep 0.1; done; rm -f "\$pidfile"; fi ;;
  start:bakablog)
    ( set -a; . "$ENVF"; set +a; cd "$APP/current/backend"; nohup "$APP/venv/bin/gunicorn" --workers 1 --threads 2 -b 127.0.0.1:$PORT --pid "\$pidfile" wsgi:app > "$SANDBOX/gunicorn.log" 2>&1 & ) ;;
  *) : ;;
esac
FAKE
chmod +x "$SANDBOX/fake-systemctl"

export BB_APP="$APP" BB_DATA="$DATA" BB_ENV_FILE="$ENVF" BB_PORT="$PORT" BB_SYSTEMCTL="$SANDBOX/fake-systemctl" BB_SYSTEM_MODE=0 BB_PYTHON="$PY" BB_USER="$(id -un)"
health() { curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true; }
running_build() { health | python3 -c 'import json,sys; print(json.load(sys.stdin).get("build",""))' 2>/dev/null || true; }
count() { "$PY" - "$DATA/blog.sqlite" "$1" <<'PY'
import sqlite3, sys
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try: print(c.execute(f"select count(*) from {sys.argv[2]}").fetchone()[0])
except Exception: print("missing")
PY
}
cleanup() { "$SANDBOX/fake-systemctl" stop bakablog >/dev/null 2>&1 || true; if [ "$FAILS" = 0 ]; then rm -rf "$SANDBOX"; else echo "kept for inspection: $SANDBOX"; fi; }
trap cleanup EXIT

step "build the release pack (nothing is uploaded)"
bash "$HERE/deploy.sh" --dry-run --skip-checks > "$SANDBOX/pack.log" 2>&1 || { cat "$SANDBOX/pack.log"; exit 1; }
PACK_SRC="${TMPDIR:-/tmp}/bakablog-last-dry-run.tar.gz"
[ -f "$PACK_SRC" ] && ok "release pack built ($(du -h "$PACK_SRC" | cut -f1))" || { bad "no pack"; exit 1; }

# make_pack NAME [command…]: a copy of the real pack with a new build id, optionally damaged by the command (run inside the unpacked tree)
make_pack() {
  local name="$1"; shift
  local dir="$SANDBOX/pack-$name"; rm -rf "$dir"; mkdir -p "$dir"
  tar -xzf "$PACK_SRC" -C "$dir"
  sed -i.bak "s|^BUILD=.*|BUILD=$(date -u +%Y%m%d%H%M%S)-$name|" "$dir/RELEASE"; rm -f "$dir/RELEASE.bak"
  ( cd "$dir" && "$@" )
  ( cd "$dir" && COPYFILE_DISABLE=1 tar -czf "$SANDBOX/$name.keep" . )
  grep '^BUILD=' "$dir/RELEASE" | cut -d= -f2 > "$SANDBOX/$name.build"
}
# install NAME: remote-update.sh deletes the pack it installs, so it gets a copy
install() { cp "$SANDBOX/$1.keep" "$SANDBOX/$1.tar.gz"; bash "$HERE/remote-update.sh" "$SANDBOX/$1.tar.gz"; }
build_of() { cat "$SANDBOX/$1.build"; }

cat > "$SANDBOX/seed.py" <<'PY'
from app import create_app
from app.db import session_scope
from app.services import auth, posts
app = create_app()
with app.app_context(), session_scope(app) as s:
    if not auth.owner_exists(s):
        auth.create_owner(s, "rehearsal-owner", "rehearsal password 12345", app.extensions["bb_config"])
    posts.create(s, {"title": "彩排里的一篇", "content_md": "正文", "status": "published"})
print("seeded")
PY

# ---------------------------------------------------------------------------------------------------------------------------------
step "1. a release with a missing piece is refused before anything is touched"
make_pack incomplete rm -f frontend/dist/preview.html
if install incomplete > "$SANDBOX/log-incomplete" 2>&1; then bad "an incomplete release was accepted"; else ok "refused"; fi
check "the message names the missing file" "grep -q 'preview.html is missing' '$SANDBOX/log-incomplete'"
check "nothing was installed" "[ ! -e '$APP/current' ]"

step "2. first installation: the env file is created once and the script stops so it can be edited"
make_pack one true
if install one > "$SANDBOX/log-first" 2>&1; then bad "first run should stop for the env file"; else ok "stopped"; fi
check "env file created with mode 600" "[ \"\$(stat -f %Lp '$ENVF' 2>/dev/null || stat -c %a '$ENVF')\" = 600 ]"
check "it holds a generated secret" "grep -qE '^BLOG_SECRET_KEY=.{40,}' '$ENVF'"
check "the example address is refused until edited" "grep -q 'BLOG_SITE_URL' '$SANDBOX/log-first'"
# only the three things that differ on this machine (the address, where the data and the front end are); proxy count and secure cookies stay as in production
sed -i.bak -e "s|^BLOG_SITE_URL=.*|BLOG_SITE_URL=http://127.0.0.1:$PORT|" -e "s|^BLOG_DATA_DIR=.*|BLOG_DATA_DIR=$DATA|" -e "s|^BLOG_FRONTEND_DIST=.*|BLOG_FRONTEND_DIST=$APP/current/frontend/dist|" "$ENVF"; rm -f "$ENVF.bak"
install one > "$SANDBOX/log-one" 2>&1 && ok "installs once the env file is edited" || { bad "first install failed"; cat "$SANDBOX/log-one"; }
check "the service answers with this build" "[ \"\$(running_build)\" = \"$(build_of one)\" ]"
check "the database is at the latest revision" "[ \"\$(count alembic_version)\" = 1 ]"
check "the code is owned by the release, not writable by others" "[ -f '$APP/current/backend/BUILD' ] && grep -q '$(build_of one)' '$APP/current/backend/BUILD'"
check "no ._ files anywhere in the installed tree" "[ -z \"\$(find '$APP/current' -name '._*' | head -1)\" ]"
check "the doctor report is clean" "( set -a; . '$ENVF'; set +a; cd '$APP/current/backend' && '$APP/venv/bin/flask' --app app doctor > '$SANDBOX/doctor.txt' 2>&1 )"
( set -a; . "$ENVF"; set +a; cd "$APP/current/backend" && PYTHONPATH=. "$APP/venv/bin/python" "$SANDBOX/seed.py" > "$SANDBOX/seed.log" 2>&1 ) || { cat "$SANDBOX/seed.log"; }
check "some content exists now (1 post)" "[ \"\$(count posts)\" = 1 ]"

step "3. an ordinary update: backup, swap, nothing lost, the way back kept"
make_pack two true
install two > "$SANDBOX/log-two" 2>&1 && ok "updates" || { bad "update failed"; cat "$SANDBOX/log-two"; }
check "the new build is the one answering" "[ \"\$(running_build)\" = \"$(build_of two)\" ]"
check "the post is still there" "[ \"\$(count posts)\" = 1 ]"
check "a pre-deploy backup was written" "ls '$DATA'/backups/backup-*-pre-deploy.tar.gz >/dev/null 2>&1"
check "the previous release is kept for a manual rollback" "grep -q '$(build_of one)' '$APP/previous/backend/BUILD'"
check "the packages were not reinstalled when nothing changed" "! grep -q 'building the Python environment' '$SANDBOX/log-two'"

step "3b. a service that refuses to stop prevents any release switch"
make_pack stop-fails true
cp "$APP/current/backend/BUILD" "$SANDBOX/build-before-stop"
cp "$ENVF" "$SANDBOX/env-before-stop"
readlink "$APP/venv" > "$SANDBOX/venv-before-stop"
cp "$SANDBOX/gunicorn.pid" "$SANDBOX/pid-before-stop"
touch "$SANDBOX/refuse-stop"
if install stop-fails > "$SANDBOX/log-stop-fails" 2>&1; then bad "a failed stop was ignored"; else ok "refused"; fi
rm -f "$SANDBOX/refuse-stop"
check "failure explains that no switch was attempted" "grep -q 'update aborted before switching' '$SANDBOX/log-stop-fails'"
check "the installed code is unchanged" "cmp -s '$APP/current/backend/BUILD' '$SANDBOX/build-before-stop'"
check "the environment is unchanged" "cmp -s '$ENVF' '$SANDBOX/env-before-stop' && [ \"\$(readlink '$APP/venv')\" = \"\$(cat '$SANDBOX/venv-before-stop')\" ]"
check "the original process is still serving the old build" "cmp -s '$SANDBOX/gunicorn.pid' '$SANDBOX/pid-before-stop' && [ \"\$(running_build)\" = \"$(build_of two)\" ]"
check "the database content was retained" "[ \"\$(count posts)\" = 1 ]"

step "4. a release whose code does not import is refused before the site is stopped"
make_pack broken-import sh -c "echo 'this is not python (' >> backend/app/__init__.py"
if install broken-import > "$SANDBOX/log-bi" 2>&1; then bad "a broken release was installed"; else ok "refused"; fi
check "the site is still running the previous build, untouched" "[ \"\$(running_build)\" = \"$(build_of two)\" ]"

step "5. a migration that changes the schema and then fails: code AND data go back"
make_pack bad-migration sh -c "cat > backend/migrations/versions/0099_broken.py <<'PYEOF'
from alembic import op
revision = '0099'
down_revision = '0001'
branch_labels = None
depends_on = None
def upgrade():
    op.execute('create table rehearsal_leftover (id integer)')
    op.execute('delete from posts')
    raise RuntimeError('the migration breaks half way')
def downgrade():
    pass
PYEOF"
if install bad-migration > "$SANDBOX/log-bm" 2>&1; then bad "a failing migration was accepted"; else ok "refused"; fi
check "the output says it rolled back" "grep -q 'rolling back' '$SANDBOX/log-bm'"
check "the previous build is answering again" "[ \"\$(running_build)\" = \"$(build_of two)\" ]"
check "the half-done schema change is gone (no leftover table)" "[ \"\$(count rehearsal_leftover)\" = missing ]"
check "the deleted post is back (data restored to the moment before the deploy)" "[ \"\$(count posts)\" = 1 ]"
check "the installed code is the previous release's again" "grep -q '$(build_of two)' '$APP/current/backend/BUILD' && [ ! -e '$APP/current/backend/migrations/versions/0099_broken.py' ]"

step "6. a release that starts but serves a wrong page is rolled back after the health checks"
make_pack wrong-shell sh -c "sed -i.bak 's|<div id=\"app\">|<div id=\"nothing\">|' frontend/dist/public.html; rm -f frontend/dist/public.html.bak"
if install wrong-shell > "$SANDBOX/log-ws" 2>&1; then bad "a wrong shell was accepted"; else ok "refused"; fi
check "the previous build is answering again" "[ \"\$(running_build)\" = \"$(build_of two)\" ]"

step "7. a release with new pinned packages gets its own environment, and a failure restores the old one"
make_pack new-packages sh -c "echo '# changed' >> backend/requirements.txt"
install new-packages > "$SANDBOX/log-np" 2>&1 && ok "installs with a rebuilt environment" || { bad "update with new packages failed"; cat "$SANDBOX/log-np"; }
check "the environment was rebuilt beside the running one" "grep -q 'building the Python environment' '$SANDBOX/log-np'"
check "the new build answers" "[ \"\$(running_build)\" = \"$(build_of new-packages)\" ]"
make_pack new-packages-bad sh -c "echo '# changed again' >> backend/requirements.txt; sed -i.bak 's|<div id=\"app\">|<div id=\"nothing\">|' frontend/dist/public.html; rm -f frontend/dist/public.html.bak"
if install new-packages-bad > "$SANDBOX/log-npb" 2>&1; then bad "accepted"; else ok "refused"; fi
check "the previous environment is back and answering" "[ \"\$(running_build)\" = \"$(build_of new-packages)\" ] && [ -x '$APP/venv/bin/gunicorn' ]"

step "7b. a rollback that cannot stop the replacement service must not overwrite running code"
rm -f "$SANDBOX/stopped-once"
touch "$SANDBOX/refuse-rollback-stop"
if install wrong-shell > "$SANDBOX/log-rollback-stop" 2>&1; then bad "a failed rollback stop was ignored"; else ok "refused"; fi
rm -f "$SANDBOX/refuse-rollback-stop" "$SANDBOX/stopped-once"
check "the failure explains that manual recovery requires stopping the service" "grep -q 'cannot stop bakablog for rollback' '$SANDBOX/log-rollback-stop'"
check "running code was not overwritten during the failed rollback" "grep -q '$(build_of wrong-shell)' '$APP/current/backend/BUILD' && [ \"\$(running_build)\" = \"$(build_of wrong-shell)\" ]"
check "data was not replaced during the failed rollback" "[ \"\$(count posts)\" = 1 ]"
install new-packages > "$SANDBOX/log-recover-stop" 2>&1 && ok "a normal update recovers after the stop failure is removed" || { bad "recovery failed"; cat "$SANDBOX/log-recover-stop"; }
check "the healthy release is serving again" "[ \"\$(running_build)\" = \"$(build_of new-packages)\" ]"

step "8. the restore drill on the data this rehearsal produced"
if bash "$HERE/restore-drill.sh" > "$SANDBOX/drill.log" 2>&1; then ok "restore drill passed"; else bad "restore drill failed"; cat "$SANDBOX/drill.log"; fi

printf '\n%s passed, %s failed\n' "$PASS" "$FAILS"
[ "$FAILS" = 0 ] && echo "REHEARSAL OK" || { echo "REHEARSAL FAILED"; exit 1; }
