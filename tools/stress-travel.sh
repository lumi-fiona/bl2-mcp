#!/usr/bin/env bash
# Travel between maps over and over, recording how much address space the game holds each time.
#
# WHY. "Ran out of video memory! Exiting..." has happened three times, every one of them during a
# map change. It is Unreal's own error (Engine/Localization/INT/Launch.int:13,
# Error_RanOutOfVideoMemory), raised when a Direct3D resource cannot be created.
#
# The thing that makes this measurable rather than a guessing game: Borderlands 2 is a 32-bit
# program, so every allocation has to fit in one 4 GB address space. VirtualMemorySize is how much
# of that space is spoken for. If it climbs with each map change and the crash comes near the
# ceiling, the cause is exhaustion and the fix is to make the game hold less. If it sits flat and
# the crash still happens, the cause is something else entirely and no amount of turning texture
# dials will help.
#
# Usage:  stress-travel.sh [rounds]        default 3 rounds through the map list
# Writes: bl2-mcp/tools/stress-travel.log

set -u
GAME="Z:/SteamLibrary/steamapps/common/Borderlands 2"
TOOLS="$GAME/bl2-mcp/tools"
LOG="$TOOLS/stress-travel.log"
ROUNDS="${1:-3}"

# Deliberately mixed: a hub, an outdoor map, an indoor map, and a big one. Travelling between
# heavy maps is where it has always failed.
MAPS=(Sanctuary Interlude Lynchwood Outwash Ash Sanctuary)

mem() {
  powershell -NoProfile -Command '
  $p = Get-Process Borderlands2 -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }
  if ($p) { "{0} {1}" -f [int]($p[0].VirtualMemorySize64/1MB), [int]($p[0].WorkingSet64/1MB) } else { "dead dead" }
  ' 2>/dev/null | tr -d '\r'
}

# The out-of-memory message is a modal dialog: the process stays alive but stops answering.
# Checking only whether the process exists would call that healthy forever.
crashed() {
  powershell -NoProfile -Command '
  Add-Type -AssemblyName Microsoft.VisualBasic 2>$null
  $w = Get-Process | Where-Object { $_.MainWindowTitle -eq "Message" }
  if ($w) { "YES" } else { "no" }
  ' 2>/dev/null | tr -d '\r'
}

say() { echo "$*" | tee -a "$LOG"; }

: > "$LOG"
say "=== travel stress, $(date) ==="
say "dxvk: $(grep -E '^d3d9\.' "$GAME/Binaries/Win32/dxvk.conf" | tr '\n' ' ')"
say "pool: $(grep -m1 '^PoolSize=' "/c/Users/Lumi/Documents/My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini")"
say ""
say "round  map          arrived  virtMB  workMB"

bash "$TOOLS/cycle.sh" >/dev/null 2>&1 || { say "FAILED: could not start the game"; exit 2; }
bash "$TOOLS/ask.sh" "$TOOLS/harness.py" >/dev/null 2>&1

n=0
for round in $(seq 1 "$ROUNDS"); do
  for map in "${MAPS[@]}"; do
    n=$((n + 1))
    echo "print(travel_to('$map'))" > /tmp/bl2-travel.py
    if ! ASK_TIMEOUT=30 bash "$TOOLS/ask.sh" /tmp/bl2-travel.py >/dev/null 2>&1; then
      say "$(printf '%5s  %-12s %s' "$round" "$map" "REFUSED THE TRAVEL REQUEST")"
    fi

    arrived="no"
    for _ in $(seq 1 25); do
      sleep 4
      if [ "$(crashed)" = "YES" ]; then
        say "$(printf '%5s  %-12s %s' "$round" "$map" "*** RAN OUT OF VIDEO MEMORY - jump number $n ***")"
        say "last known: $(mem)"
        exit 1
      fi
      here=$(echo 'print(where())' | ASK_TIMEOUT=20 bash "$TOOLS/ask.sh" 2>/dev/null | tail -1)
      case "$here" in *"$map"*) arrived="yes"; break;; esac
    done

    read -r virt work <<<"$(mem)"
    say "$(printf '%5s  %-12s %-8s %6s  %6s' "$round" "$map" "$arrived" "$virt" "$work")"
    if [ "$virt" = "dead" ]; then
      say "*** the process died on jump number $n ***"
      exit 1
    fi
  done
done

say ""
say "survived $n map changes"
