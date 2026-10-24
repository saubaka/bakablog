#!/bin/zsh
# The admin's browser checks in Chromium and WebKit. They run against the SEPARATE QA instance (BB_ADMIN_URL, default http://127.0.0.1:5310 with its own data
# and an administrator whose credentials are in backend/data-qa/credentials.json) — never against a real site: the flows create, change and restore data.
# Prepare: `npm run build`, start the QA instance (see docs/ADMIN.md). Usage: zsh qa/admin.sh [chromium|webkit]
cd "${0:A:h}/.." || exit 1
if [ $# -gt 0 ]; then engines=("$@"); else engines=(chromium webkit); fi
fail=0
for engine in $engines; do
  echo "################ $engine"
  for audit in admin-pages admin-audit admin-flows admin-editors; do
    echo "=== $audit ($engine)"
    out=$(BROWSER=$engine node qa/$audit.mjs 2>&1); code=$?
    print -r -- "$out" | tail -${TAILN:-12}
    # a failure is reported with the lines that say what failed, not only with the last few lines of output
    [ $code -eq 0 ] || { print -r -- "$out" | grep -E '✗|^    |problem' | head -${FAILN:-25}; echo "!!! FAILED: $audit ($engine)"; fail=1; }
  done
done
echo; [ $fail -eq 0 ] && echo "ALL ADMIN CHECKS PASSED" || echo "SOME ADMIN CHECKS FAILED"
exit $fail
