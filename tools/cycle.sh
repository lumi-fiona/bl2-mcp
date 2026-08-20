#!/usr/bin/env bash
# Restart Borderlands 2 and put a character in the world, with no keypress and no stolen focus.
#
# WHY THIS EXISTS. Python files inside the mod are read once, when the game loads them. Editing
# one changes nothing in a running game. So a night spent editing and testing without this in
# between is a night spent testing the old code, where a correct fix reports itself as a failure
# and looks exactly like a real one. That is the single most expensive way to be wrong.
#
# Run this after every edit to anything under sdk_mods/, and after every crash.
#
# Every step below was measured on 2026-08-19 rather than guessed:
#   - the game must be killed first: two instances at once exhausted the 32-bit memory ceiling
#     and produced "Ran out of video memory! Exiting..." mid-travel, and they also race for the
#     bridge's one request file
#   - the bridge comes alive on the title screen about 12 seconds in, with no input
#   - BeginStartupProcess() walks the legal screen to the main menu
#   - LoadLastSavedSaveGame() then LaunchSaveGame(0) puts the character in the world
#   - faking keypresses does NOT work: InputKey and the movie's own key handler both return False
#
# Usage:  cycle.sh            launch and load the last character
#         cycle.sh --menu     launch and stop at the main menu

set -u
GAME="D:/SteamLibrary/steamapps/common/Borderlands 2"
EXE_DIR="$GAME/Binaries/Win32"
B="$GAME/sdk_mods/bl2_modern/data/bridge"
TOOLS="$GAME/bl2-mcp/tools"
STOP_AT_MENU="${1:-}"

say() { echo "[cycle] $*"; }

# --- 1. nothing else may be running -------------------------------------------------------
taskkill //F //IM Borderlands2.exe >/dev/null 2>&1
powershell -NoProfile -Command 'Get-Process Borderlands2 -ErrorAction SilentlyContinue | Stop-Process -Force' >/dev/null 2>&1
for _ in $(seq 1 20); do
  bash "$TOOLS/alive.sh" >/dev/null || break
  sleep 0.5
done
if pids=$(bash "$TOOLS/alive.sh"); then
  say "FAILED: Borderlands 2 is still live as pid(s) $pids. Not launching a second one."
  exit 2
fi

rm -f "$B/heartbeat.txt" "$B/response.txt" "$B/request.py"
rm -f "$EXE_DIR/Plugins/unrealsdk.log"

# --- 2. launch, no launcher, no movies ----------------------------------------------------
say "launching"
( cd "$EXE_DIR" && cmd //c start "" Borderlands2.exe -NoLauncher -nostartupmovies )

# --- 3. wait for the bridge (it ticks on the title screen, no input needed) ----------------
for i in $(seq 1 40); do
  sleep 2
  [ -f "$B/heartbeat.txt" ] && { say "bridge alive after $((i*2))s"; break; }
done
if [ ! -f "$B/heartbeat.txt" ]; then
  say "FAILED: the bridge never came alive. The mod may not have loaded - check unrealsdk.log."
  exit 2
fi

# --- 4. legal screen -> main menu ---------------------------------------------------------
say "walking the startup process"
ASK_TIMEOUT=30 bash "$TOOLS/ask.sh" <<'PY' >/dev/null
import unrealsdk
m = [o for o in unrealsdk.find_all("WillowGFxMoviePressStart") if not o.Name.startswith("Default__")]
print("BeginStartupProcess ->", m[0].BeginStartupProcess() if m else "NO PRESS-START MOVIE")
PY

for i in $(seq 1 30); do
  sleep 2
  out=$(ASK_TIMEOUT=20 bash "$TOOLS/ask.sh" <<'PY'
import unrealsdk
fe = [o for o in unrealsdk.find_all("FrontendGFxMovie") if not o.Name.startswith("Default__")]
print("MENU" if fe else "waiting")
PY
)
  case "$out" in *MENU*) say "main menu after $((i*2))s"; break;; esac
done
case "${out:-}" in *MENU*) ;; *) say "FAILED: never reached the main menu"; exit 2;; esac

if [ "$STOP_AT_MENU" = "--menu" ]; then
  say "stopped at the main menu as asked"
  exit 0
fi

# --- 5. main menu -> in the world ---------------------------------------------------------
say "loading the last character"
ASK_TIMEOUT=30 bash "$TOOLS/ask.sh" <<'PY' >/dev/null
import unrealsdk
pc = [o for o in unrealsdk.find_all("WillowPlayerController") if not o.Name.startswith("Default__")][-1]
pc.LoadLastSavedSaveGame()
print("cached:", pc.HasCachedSaveGame())
PY
sleep 3
ASK_TIMEOUT=30 bash "$TOOLS/ask.sh" <<'PY' >/dev/null
import unrealsdk
fe = [o for o in unrealsdk.find_all("FrontendGFxMovie") if not o.Name.startswith("Default__")][0]
fe.LaunchSaveGame(0)
print("launched")
PY

# The map name alone lies - it reports a map before the map's contents exist. Wait for a
# backpack that can actually be counted.
for i in $(seq 1 40); do
  sleep 3
  out=$(ASK_TIMEOUT=25 bash "$TOOLS/ask.sh" <<'PY'
import unrealsdk
pcs = [o for o in unrealsdk.find_all("WillowPlayerController") if not o.Name.startswith("Default__")]
pc = pcs[-1] if pcs else None
try:
    n = len(list(pc.GetPawnInventoryManager().Backpack))
except Exception:
    n = -1
print("READY" if (pc and pc.Pawn is not None and n >= 0) else "waiting",
      pc.WorldInfo.GetMapName(False) if pc else "?", n)
PY
)
  case "$out" in *READY*) say "in the world after $((i*3))s: ${out##*READY}"; exit 0;; esac
done

say "FAILED: a character never finished loading"
exit 2
