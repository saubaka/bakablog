#!/bin/zsh
# Runs every browser check against a RUNNING server (BB_URL, default http://127.0.0.1:5300) in Chromium and WebKit.
# Prepare: `npm run build`, restart `make -C backend serve`, demo content (`flask --app app seed-demo`). Usage: sh qa/all.sh [chromium|webkit]
cd "${0:A:h}/.." || exit 1
if [ $# -gt 0 ]; then engines=("$@"); else engines=(chromium webkit); fi
fail=0
for engine in $engines; do
  echo "################ $engine"
  for audit in overflow lines contrast focus nav pull text fx coverage csp a11y flows; do
    echo "=== $audit ($engine)"
    out=$(BROWSER=$engine node qa/$audit.mjs 2>&1); code=$?
    print -r -- "$out" | tail -${TAILN:-8}
    # a failure is reported with the lines that say what failed, not only with the last few lines of output
    [ $code -eq 0 ] || { print -r -- "$out" | grep -E '✗|^    |problem' | head -${FAILN:-25}; echo "!!! FAILED: $audit ($engine)"; fail=1; }
  done
done
echo; [ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $fail
