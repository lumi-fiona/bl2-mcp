#!/usr/bin/env bash
# Run a check script that damages things, then put the character back exactly as it was.
#
#   guard.sh bl2-mcp/tools/checks/grinder.py
#
# WHY IT IS NOT JUST A FILE COPY. A character's inventory lives in the running game's memory, not
# in the save file. Deleting an item and then copying the old save back changes nothing that is
# loaded - and the game's next autosave writes the damaged inventory straight over the file you
# just restored. So the restore has to end with the game re-reading the file, which means a reload.
#
# That was the review's finding on 2026-08-19, and it is the difference between a guard and a
# comforting ritual.
#
# THE CHECK THAT MATTERS: this script confirms the damage HAPPENED before it confirms the damage
# was undone. A restore that silently does nothing looks identical to a test that changed nothing,
# and a guard nobody can distinguish from a no-op is worse than none, because it is trusted.

set -u
GAME="D:/SteamLibrary/steamapps/common/Borderlands 2"
TOOLS="$GAME/bl2-mcp/tools"
SAVES="/c/Users/Lumi/Documents/My Games/Borderlands 2/WillowGame/SaveData/76561198860136601"
STAMP=$(date +%Y%m%d-%H%M%S)
HOLD="$GAME/BACKUP-guard-$STAMP"
SCRIPT="${1:?usage: guard.sh <check-script>}"

say() { echo "[guard] $*"; }

count_items() {
  echo 'print("ITEMS", len(backpack()) + len(equipped()))' \
    | ASK_TIMEOUT=30 bash "$TOOLS/ask.sh" 2>/dev/null | grep -o "ITEMS [0-9]*" | tail -1
}

# --- 1. take a fresh copy. Never reuse an old one: a backup from before tonight's play would
#        roll Lumi back past everything they did today.
mkdir -p "$HOLD"
cp -r "$SAVES/." "$HOLD/" || { say "FAILED: could not copy the saves"; exit 2; }
say "held $(find "$HOLD" -type f | wc -l) save files in $(basename "$HOLD")"

before=$(count_items)
say "before: $before"

# --- 2. run the damage
say "running $(basename "$SCRIPT")"
ASK_TIMEOUT=120 bash "$TOOLS/ask.sh" "$SCRIPT"
rc=$?

after=$(count_items)
say "after:  $after"

# --- 3. put it back: files first, then make the game re-read them
say "restoring"
cp -r "$HOLD/." "$SAVES/" || { say "FAILED: could not restore - the copy is still in $HOLD"; exit 2; }
bash "$TOOLS/cycle.sh" >/dev/null 2>&1 || { say "FAILED: could not reload the character"; exit 2; }
bash "$TOOLS/ask.sh" "$TOOLS/harness.py" >/dev/null 2>&1

restored=$(count_items)
say "restored: $restored"

# --- 4. say honestly what this run proved
if [ "$before" = "$restored" ]; then
  if [ "$before" = "$after" ]; then
    say "the item count never moved, so this run does NOT show the guard works - it shows the"
    say "check was harmless. Do not treat that as a passing restore."
  else
    say "damage happened and was undone. The guard is doing its job."
  fi
else
  say "*** THE RESTORE DID NOT WORK: $before before, $restored after. The copy is in $HOLD. ***"
  exit 2
fi

exit $rc
