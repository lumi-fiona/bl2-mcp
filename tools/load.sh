#!/usr/bin/env bash
# Load the most recent character and WAIT until the backpack is actually readable.
S="$(dirname "$0")"
for attempt in 1 2 3; do
  powershell -NoProfile -Command '$w=New-Object -ComObject wscript.shell; if($w.AppActivate("Borderlands 2")){Start-Sleep -Milliseconds 400; $w.SendKeys("{ENTER}")}' >/dev/null 2>&1
  for _ in $(seq 1 20); do
    sleep 3
    out=$(echo 'import unrealsdk
pc=unrealsdk.find_all("WillowPlayerController")[-1]
try:
    n=len(list(pc.GetPawnInventoryManager().Backpack))
except Exception:
    n=-1
print("READY" if (pc.Pawn is not None and n>0) else "waiting", pc.WorldInfo.GetMapName(False), n)' | bash "$S/ask.sh" 2>/dev/null | tail -1)
    case "$out" in READY*) echo "$out"; exit 0;; esac
  done
  echo "attempt $attempt did not load, retrying"
done
echo "FAILED to load a character"; exit 1
