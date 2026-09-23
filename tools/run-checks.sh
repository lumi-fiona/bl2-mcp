#!/usr/bin/env bash
# Run every check and total them up.
#
#   run-checks.sh            everything
#   run-checks.sh grinder    only files whose name contains "grinder"
#
# The in-game ones need a character loaded - run cycle.sh first. Files ending -files.py are
# ordinary Python and are run outside the game. Files ending -needs-travel.py are skipped here
# and named at the end, because they need map changes driven from outside a request.

set -u
GAME="Z:/SteamLibrary/steamapps/common/Borderlands 2"
TOOLS="$GAME/bl2-mcp/tools"
CHECKS="$TOOLS/checks"
FILTER="${1:-}"
OUT="$CHECKS/RESULTS.txt"

: > "$OUT"
skipped=()

for f in "$CHECKS"/*.py; do
  name=$(basename "$f" .py)
  [ -n "$FILTER" ] && case "$name" in *"$FILTER"*) ;; *) continue;; esac

  case "$name" in
    *-needs-travel) skipped+=("$name"); continue;;
  esac

  echo "##### $name #####" | tee -a "$OUT"
  case "$name" in
    *-files)
      PYTHONIOENCODING=utf-8 python "$f" 2>&1 | tee -a "$OUT" | grep -E "^\s*[0-9]+/[0-9]+ passed" || true
      ;;
    *)
      # The harness goes in fresh before every file. The bridge keeps ONE scope alive for the
      # whole session, so anything a check file leaves behind under a name the harness also uses
      # - `check` itself, most damagingly - is still there for the next file. Measured
      # 2026-08-20: a scratch script that defined its own `check` made the file after it report
      # "0/0 passed" while printing thirty passes, because the results were going into a list
      # nothing summarised. One round trip a file is a cheap price for a number that means
      # something.
      bash "$TOOLS/ask.sh" "$TOOLS/harness.py" >/dev/null 2>&1
      ASK_TIMEOUT=180 bash "$TOOLS/ask.sh" "$f" 2>&1 | tee -a "$OUT" | grep -E "^\s*[0-9]+/[0-9]+ passed" || true
      # If that check killed the game, say which one and stop. Carrying on would report every
      # remaining file as broken and bury the one that actually did it.
      if powershell -NoProfile -ExecutionPolicy Bypass -File "$TOOLS/crashwatch.ps1" 2>/dev/null | grep -q crashdialog; then
        echo "*** $name CRASHED THE GAME - stopping here ***" | tee -a "$OUT"
        powershell -NoProfile -ExecutionPolicy Bypass -File "$TOOLS/crashwatch.ps1" 2>/dev/null | tee -a "$OUT"
        exit 1
      fi
      ;;
  esac
done

echo
echo "=== TOTAL ==="
PYTHONIOENCODING=utf-8 python - "$OUT" <<'PY'
import re, sys, collections
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
passed = len(re.findall(r"^\[PASS\]", text, re.M))
failed = len(re.findall(r"^\[FAIL\]", text, re.M))
errors = len(re.findall(r"^!!! ", text, re.M)) + text.count("--- it raised ---")
print(f"{passed} passed, {failed} failed, {errors} scripts errored, {passed+failed} checks ran")
PY

if [ ${#skipped[@]} -gt 0 ]; then
  echo
  echo "not run (need map changes driven from outside a request): ${skipped[*]}"
fi
echo "full output in $OUT"
