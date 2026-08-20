#!/usr/bin/env bash
# Exit 0 if a LIVE Borderlands 2 is running, 1 if not. Prints the pids it found alive.
#
# Why this is not just `tasklist`: measured 2026-08-19, after the game died of "Ran out of video
# memory", two processes stayed in tasklist for many minutes with unchanging memory figures while
# taskkill answered "there is no running instance of the task". Windows keeps the entry after the
# process has gone when termination stalls - which a graphics driver hang will do.
#
# `HasExited` is the truth. tasklist is a stale snapshot, and believing it means either refusing
# to launch forever or launching a second copy on top of a live one. Both happened tonight.

out=$(powershell -NoProfile -Command '
$p = Get-Process Borderlands2 -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }
if ($p) { ($p | ForEach-Object { $_.Id }) -join "," } else { "" }
' 2>/dev/null | tr -d '\r')

if [ -n "$out" ]; then
  echo "$out"
  exit 0
fi
exit 1
