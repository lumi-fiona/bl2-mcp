#!/usr/bin/env bash
# Put the save folder back to a backup taken at the start of a job.
#
#   clean-throwaways.sh <backup-dir> [--restore] [--dry-run]
#
# <backup-dir> must be under .scratch/playthrough/backups/ and hold a copy of the save folder
# (its 76561198860136601/ subfolder, as every job's first step makes it).
#
# Always: deletes save-folder files that do NOT exist in the backup - the throwaway characters a
# job created. A file that exists in the backup is never deleted.
# --restore: also copies back every file whose content differs from the backup.
# Refuses outright when the backup is 12 hours old or more, so real play since then can never be
# deleted or rolled back. Refuses while the game is running.
# --dry-run: prints what it would do and changes nothing.
set -euo pipefail

GAME="Z:/SteamLibrary/steamapps/common/Borderlands 2"
SAVE="/c/Users/Lumi/Documents/My Games/Borderlands 2/WillowGame/SaveData/76561198860136601"
MAX_AGE_HOURS=12

backup="${1:-}"; shift || true
restore=0; dry=0
for a in "$@"; do
  case "$a" in
    --restore) restore=1 ;;
    --dry-run) dry=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

[ -n "$backup" ] || { echo "usage: $0 <backup-dir> [--restore] [--dry-run]" >&2; exit 2; }
backup="$(cd "$backup" 2>/dev/null && pwd -W)" || { echo "no such backup: $backup" >&2; exit 2; }
case "$backup" in
  "$GAME/.scratch/playthrough/backups/"*) ;;
  *) echo "refused: the backup must be under $GAME/.scratch/playthrough/backups/" >&2; exit 2 ;;
esac
copy="$backup/76561198860136601"
[ -d "$copy" ] || { echo "refused: $copy is missing - not a save-folder backup" >&2; exit 2; }
[ -n "$(ls -A "$copy")" ] || { echo "refused: the backup is empty" >&2; exit 2; }
if tasklist 2>/dev/null | grep -qi "Borderlands2.exe"; then
  echo "refused: the game is running - close it first" >&2; exit 2
fi

# Both deleting and restoring trust the backup to describe "before this job", so an old backup is
# refused outright: a character Lumi made since would otherwise look like a throwaway.
age_h=$(( ( $(date +%s) - $(stat -c %Y "$copy") ) / 3600 ))
if [ "$age_h" -ge "$MAX_AGE_HOURS" ]; then
  echo "refused: the backup is ${age_h}h old (limit ${MAX_AGE_HOURS}h) - real play may have happened since" >&2
  exit 3
fi

run() { if [ "$dry" = 1 ]; then echo "would: $*"; else "$@"; fi; }

deleted=0; restored=0
while IFS= read -r -d '' f; do
  rel="${f#"$SAVE"/}"
  if [ ! -e "$copy/$rel" ]; then
    echo "delete (not in backup): $rel"; run rm -f -- "$f"; deleted=$((deleted + 1))
  fi
done < <(find "$SAVE" -type f -print0)

if [ "$restore" = 1 ]; then
  while IFS= read -r -d '' b; do
    rel="${b#"$copy"/}"
    if ! cmp -s "$b" "$SAVE/$rel" 2>/dev/null; then
      echo "restore (differs from backup): $rel"; run mkdir -p "$(dirname "$SAVE/$rel")"; run cp -p -- "$b" "$SAVE/$rel"
      restored=$((restored + 1))
    fi
  done < <(find "$copy" -type f -print0)
fi

left=0
while IFS= read -r -d '' b; do
  rel="${b#"$copy"/}"; cmp -s "$b" "$SAVE/$rel" 2>/dev/null || left=$((left + 1))
done < <(find "$copy" -type f -print0)
echo "deleted $deleted, restored $restored, still differing from backup: $left"
