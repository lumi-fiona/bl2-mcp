#!/usr/bin/env bash
# Send Python into the running game and print what comes back.
#
#   ask.sh <file-with-python>     or     echo 'print(1)' | ask.sh
#
# Two things this does beyond writing a file, both added 2026-08-19 after a review found the
# failure modes:
#
#   1. Every request carries a unique marker and the answer is rejected unless it carries the
#      same one. Without this, a response left behind by a request that timed out during a map
#      load gets read as the answer to the NEXT question - which marks the wrong check passed.
#
#   2. A timeout distinguishes "the game is gone" from "the game is busy". The bridge only runs
#      inside PlayerTick, so during a level load it legitimately stops answering for many
#      seconds. Treating that as death and killing the process would mean killing during the
#      save-on-travel window, which is the one thing here that loses real data.
#
# ASK_TIMEOUT=<seconds> overrides the default wait. Loads want 90 or more.

B="Z:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/bl2_modern/data/bridge"
TIMEOUT="${ASK_TIMEOUT:-40}"
ID="ask-$$-${RANDOM}${RANDOM}"

# Checking aliveness costs a PowerShell start, so it is NOT done before every request - only on
# the failure path, where the answer decides between "loading" and "dead". See alive.sh for why
# tasklist cannot be trusted for this.
alive() { bash "$(dirname "$0")/alive.sh" >/dev/null 2>&1; }

mkdir -p "$B"
rm -f "$B/response.txt" "$B/request.py"

# The marker goes at the END, never the start. Put it first and it displaces
# `from __future__ import annotations`, which Python requires to be the first statement in a
# compiled unit - the whole request then fails to compile, so the marker never prints, so this
# script waits out its full timeout on a request that was answered instantly. Cost: one wasted
# forty-second wait on 2026-08-19 before anyone read the response file.
{
  if [ $# -ge 1 ]; then cat "$1"; else cat; fi
  printf '\nprint("%s")\n' "$ID"
} > "$B/request.py.part"
mv "$B/request.py.part" "$B/request.py"

deadline=$(( $(date +%s) + TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 0.5
  if [ -f "$B/response.txt" ]; then
    # response.txt was deleted above, and cycle.sh guarantees exactly one game is running, so
    # anything here now is the answer to this request. The marker is a confirmation, not a
    # requirement - code that raises never reaches its last line, and that traceback is
    # precisely the answer worth reading.
    if grep -q "$ID" "$B/response.txt"; then
      grep -v "^$ID$" "$B/response.txt"
    else
      echo "!!! this request did not run to the end - it raised, or it never got there:"
      cat "$B/response.txt"
    fi
    exit 0
  fi
done

# Timed out. Take the orphan request away so it cannot run late and confuse the next call.
rm -f "$B/request.py"
if alive; then
  # A crashed game is still a live process sitting behind a modal box, so "alive" alone would
  # report a corpse as healthy for the rest of an unattended run. Read the box.
  crash=$(powershell -NoProfile -ExecutionPolicy Bypass -File "$(dirname "$0")/crashwatch.ps1" 2>/dev/null)
  case "$crash" in
    *crashdialog*)
      echo "!!! THE GAME HAS CRASHED and is showing a message box:"
      echo "$crash" | sed -n '3,40p'
      exit 4
      ;;
  esac
  echo "!!! no answer in ${TIMEOUT}s, but the game process is ALIVE and shows no crash box."
  echo "!!! that means loading, a frozen frame, or a request that never returns."
  echo "!!! heartbeat: $(cat "$B/heartbeat.txt" 2>/dev/null || echo none)"
  exit 3
fi
echo "!!! the game died while answering"
exit 2
