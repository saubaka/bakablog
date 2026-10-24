#!/bin/zsh
# Runs every automated check against the dev server (python3 serve.py 5200). Needs CHROME and NODE_PATH, see README.md.
cd "${0:A:h}/.." || exit 1
fail=0
run() { echo "=== $*"; "$@" 2>&1 | tail -${TAILN:-6}; [ ${pipestatus[1]} -eq 0 ] || { echo "!!! FAILED: $*"; fail=1; }; }
run node qa/overflow.js
run node qa/lines-audit.js
run node qa/contrast-audit.js
run node qa/focus-audit.js
run node qa/nav-audit.js
run node qa/text-audit.js
run node qa/selftest.js
for p in home blog post moments archive 404 components fx-lab index; do PAGE=$p TAILN=2 run node qa/fx-audit.js; done
echo; [ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $fail
