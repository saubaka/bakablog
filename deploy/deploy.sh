#!/usr/bin/env bash
# Build, package, upload and install a release.   Run it from your Mac:
#
#   deploy/deploy.sh HOST                      # HOST is whatever `ssh HOST` already reaches (key login), root or a user with passwordless sudo
#   deploy/deploy.sh HOST --dry-run            # everything except touching the server: runs the checks, builds, packs, prints what would be uploaded
#   deploy/deploy.sh HOST --skip-checks        # skip the test suites (the build's own checks still run)
#   deploy/deploy.sh HOST --url https://blog.example.com   # also check the public address afterwards from here
#
# What it does: tests → build → pack (COPYFILE_DISABLE, no ._* files, no data, no secrets, no .venv) → refuse if anything names an AI →
# upload the pack and remote-update.sh → run it (see there: backup, stop, swap, migrate, self-check, start, check, automatic rollback).
# Nothing here ever prints or stores a password or a token.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST=""; DRY=0; SKIP=0; URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --skip-checks) SKIP=1 ;;
    --url) URL="${2:?--url needs an address}"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) [ -z "$HOST" ] && HOST="$1" || { echo "one HOST only" >&2; exit 2; } ;;
  esac
  shift
done
[ -n "$HOST" ] || [ "$DRY" = 1 ] || { echo "usage: deploy/deploy.sh HOST [--dry-run] [--skip-checks] [--url https://…]" >&2; exit 2; }

say() { printf '\033[1m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[deploy] %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 1. checks and build ------------------------------------------------------------------------------------------------------------
if [ "$SKIP" = 0 ]; then
  say "backend: ruff + tests"
  (cd "$ROOT/backend" && .venv/bin/ruff check app tests && .venv/bin/python -m pytest)
  say "frontend: typecheck + lint + unit tests"
  (cd "$ROOT/frontend" && npm run check)
fi
say "frontend: build (typecheck, vite, postbuild: CSP, budgets, shells)"
(cd "$ROOT/frontend" && npm run build)

# ---- 2. stage what the server needs --------------------------------------------------------------------------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bakablog-release.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
STAGE="$WORK/stage"
mkdir -p "$STAGE/backend" "$STAGE/frontend" "$STAGE/deploy" "$STAGE/docs"
rsync -a --exclude='.venv' --exclude='data' --exclude='data-qa' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' \
      --exclude='.coverage' --exclude='.env' --exclude='tests' --exclude='BUILD' --exclude='._*' --exclude='.DS_Store' --exclude='Makefile' \
      "$ROOT/backend/" "$STAGE/backend/"
rsync -a --exclude='._*' --exclude='.DS_Store' "$ROOT/frontend/dist/" "$STAGE/frontend/dist/"
rsync -a --exclude='._*' --exclude='.DS_Store' --exclude='rehearsal' --exclude='.last-dry-run' "$HERE/" "$STAGE/deploy/"
rsync -a --exclude='._*' --exclude='.DS_Store' --exclude='agent-memory' --exclude='handoff' "$ROOT/docs/" "$STAGE/docs/"   # the private working notes for whoever continues the project stay out of the release
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/backend/app/version.py")"
[ -n "$VERSION" ] || die "cannot read the version"
FINGER="$(cd "$STAGE" && find . -type f | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256 | cut -c1-8)"
BUILD="$(date -u +%Y%m%d%H%M%S)-$FINGER"
printf 'VERSION=%s\nBUILD=%s\nCREATED=%s\n' "$VERSION" "$BUILD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STAGE/RELEASE"
find "$STAGE" -name '._*' -delete

# ---- 3. what must never ship ----------------------------------------------------------------------------------------------------------
# (the words are split below so that this very file does not trip its own check)
FORBIDDEN='cl''aude|anth''ropic|co-auth''ored-by|generated w''ith'
if grep -rIilE "$FORBIDDEN" "$STAGE" >/dev/null 2>&1; then
  grep -rIilE "$FORBIDDEN" "$STAGE" | head -5 >&2
  die "a file in the release names an AI tool or carries a credit line; remove it (the project ships without any)"
fi
for pattern in 'credentials.json' 'setup-token.txt' '.dev-secret' '*.sqlite' '*.sqlite-wal' '*.pem' 'production.env'; do
  if find "$STAGE" -name "$pattern" | grep -q .; then find "$STAGE" -name "$pattern" >&2; die "the release contains $pattern"; fi
done
[ -f "$STAGE/frontend/dist/public.html" ] && [ -f "$STAGE/frontend/dist/admin.html" ] && [ -f "$STAGE/frontend/dist/preview.html" ] || die "frontend/dist is incomplete"

PACK="$WORK/bakablog-$VERSION-$BUILD.tar.gz"
( cd "$STAGE" && COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata --exclude='._*' -czf "$PACK" . 2>/dev/null || COPYFILE_DISABLE=1 tar --exclude='._*' -czf "$PACK" . )
tar -tzf "$PACK" | grep -q '/\._' && die "the pack contains AppleDouble (._*) files"
say "release $VERSION build $BUILD: $(du -h "$PACK" | cut -f1), $(tar -tzf "$PACK" | wc -l | tr -d ' ') entries"

if [ "$DRY" = 1 ]; then
  say "dry run: nothing was uploaded. The pack would go to $HOST:/tmp and remote-update.sh would install it."
  LAST="${TMPDIR:-/tmp}/bakablog-last-dry-run.tar.gz"
  cp "$PACK" "$LAST" && say "copy of the pack: $LAST"
  exit 0
fi

# ---- 4. upload and run ----------------------------------------------------------------------------------------------------------------
REMOTE_DIR="/tmp/bakablog-deploy-$BUILD"
say "uploading to $HOST"
ssh "$HOST" "mkdir -p '$REMOTE_DIR' && chmod 700 '$REMOTE_DIR'"
scp -q "$PACK" "$STAGE/deploy/remote-update.sh" "$HOST:$REMOTE_DIR/"
say "installing (the server script prints its own progress; it rolls back by itself on failure)"
set +e
ssh -t "$HOST" "cd '$REMOTE_DIR' && bash remote-update.sh '$REMOTE_DIR/$(basename "$PACK")'"
CODE=$?
set -e
ssh "$HOST" "rm -rf '$REMOTE_DIR'" || true
[ "$CODE" = 0 ] || die "the server install failed (exit $CODE); the server rolled back if it got far enough"

# ---- 5. look from outside --------------------------------------------------------------------------------------------------------------
if [ -n "$URL" ]; then
  say "checking $URL from here"
  health="$(curl -fsS --max-time 15 "$URL/api/health")" || die "$URL/api/health did not answer"
  printf '%s' "$health" | grep -q "\"build\":\"$BUILD\"" || die "$URL reports a different build: $health"
  for path in / /blog /moments /feed/posts.xml /sitemap.xml /admin/; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$URL$path")"
    [ "$code" = 200 ] || die "$URL$path answered $code"
  done
  say "public address OK"
fi
say "done: $VERSION build $BUILD"
