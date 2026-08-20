#!/usr/bin/env bash
# Launch Borderlands 2 and leave it running, past the press-any-key screen.
GAME="D:/SteamLibrary/steamapps/common/Borderlands 2"
LOG="$GAME/Binaries/Win32/Plugins/unrealsdk.log"
taskkill //F //IM Borderlands2.exe >/dev/null 2>&1; sleep 2; rm -f "$LOG"
cd "$GAME/Binaries/Win32" || exit 1
nohup "./Borderlands2.exe" -NoLauncher -nostartupmovies >/dev/null 2>&1 &
for i in $(seq 1 70); do
  sleep 3
  if grep -q "core.py@.*loaded" "$LOG" 2>/dev/null; then sleep 6; echo "up"; exit 0; fi
  # Only press keys when explicitly allowed. Sending a key means pulling the game window to
  # the front and typing into it, which lands in whatever Lumi is doing if she is at the PC.
  if [ "$i" -ge 4 ] && [ "${BL2_STEAL_FOCUS:-0}" = "1" ]; then
    powershell -NoProfile -Command '$w=New-Object -ComObject wscript.shell; if($w.AppActivate("Borderlands 2")){Start-Sleep -Milliseconds 250; $w.SendKeys(" ")}' >/dev/null 2>&1
  fi
done
echo "FAILED to reach the menu"; exit 1
