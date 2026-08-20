# Grinder at the real Golden Chest - the half of AUDIT-RAW/grinder.md claim 6 that needs a
# body standing in Sanctuary, plus the real-world half of claim 9 ('Open the chest normally').
#
# THE SEQUENCE. None of it can happen inside one request: a map change needs the very frame a
# request is holding, and the chest has to be pressed by a person.
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   2. bash bl2-mcp/tools/ask.sh <(echo 'print(sorted(stations()))')
#        - find Sanctuary's station in that list; it is not necessarily called "Sanctuary"
#   3. bash bl2-mcp/tools/ask.sh <(echo 'travel_to("<the name from step 2>")')
#        - returns immediately; the map change happens over the next several seconds
#   4. sleep 60                       # the SHELL waits. Never the game.
#   5. bash bl2-mcp/tools/ask.sh <(echo 'print(where())')      # confirm the map really changed
#   6. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/grinder-needs-travel.py   # run 1, arms it
#   7. BY HAND: walk into the Golden Chest and press Use, with zero Golden Keys - that is the
#      whole case. Then press escape to dismiss whatever the grinder put on screen.
#   8. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/grinder-needs-travel.py   # run 2, reads it
#
# Run 1 finds the chest, stands you behind it, and turns the 'Log every interactive object
# used' switch on so that step 7 leaves a durable line in data/grinder-findings.txt. Run 2
# reads the lines that appeared in between and puts that switch back where it was.
#
# It moves your pawn. That is the point of the file, but it is the one thing here that is not
# put back afterwards - there is nothing to put it back to.
#
# NOT covered here: claim 31, a perfected item surviving save/quit/reload. That needs a
# keypress on the character-select screen (bl2-mcp/tools/load.sh, which steals the foreground
# window), which is a different kind of "not in one request" and belongs in its own file.

reset()
import traceback
import unrealsdk
from pathlib import Path
from bl2_modern.features import grinder as G

P = pc()
FINDINGS = Path(G.__file__).parent.parent / "data" / "grinder-findings.txt"
SIZE = FINDINGS.stat().st_size if FINDINGS.exists() else 0
HERE = where()

chest = G._chest_actor()
check(
    "the Golden Chest is loaded in the map we are standing in",
    chest is not None,
    f"map {HERE}, chest {chest}",
)
check(
    "the actor the grinder calls the chest really is the Golden Chest",
    chest is not None and "TreasureChest_Golden" in str(chest.InteractiveObjectDefinition),
    str(chest.InteractiveObjectDefinition) if chest is not None else "no chest here",
)

try:
  if "GRINDER_CHEST_MARK" not in globals():
    # ---- run 1: arm it -------------------------------------------------------------------
    GRINDER_CHEST_MARK = SIZE
    GRINDER_CHEST_DIAGNOSE = G.diagnose.value
    GRINDER_CHEST_MAP = HERE
    G.diagnose.value = True
    G._busy = False
    G._skip_once = False
    if chest is not None:
        move_to_actor(chest)
    print(
        f"\narmed at byte {SIZE} of {FINDINGS.name}, in {HERE}, standing behind the chest.\n"
        "Now press Use on it with no Golden Keys, dismiss whatever appears, and run this file "
        "again to read the result.",
    )
  else:
    # ---- run 2: read what the chest press left behind ---------------------------------------
    text = FINDINGS.read_text(encoding="utf-8", errors="replace") if FINDINGS.exists() else ""
    fresh = [line for line in text[GRINDER_CHEST_MARK:].splitlines() if line.strip()]
    about_chest = [line for line in fresh if "TreasureChest_Golden" in line]
    caught_by = sorted({line.split("]")[0].lstrip("[") for line in about_chest if line.startswith("[")})

    check(
        "pressing Use on the real Golden Chest reaches the grinder at all",
        bool(about_chest),
        f"{len(fresh)} new lines since run 1, {len(about_chest)} of them about the chest",
    )
    check(
        "the hook the pack was built around, 'could not afford', is the one that fires",
        "could not afford" in caught_by,
        f"hooks that caught this press: {caught_by or 'none'}",
    )
    check(
        "one chest press is caught by exactly one hook, so 'Open the chest normally' can work",
        len(caught_by) == 1,
        f"{len(caught_by)} hooks caught one press: {caught_by} - _skip_once is a single global "
        f"and the first of them consumes it (grinder.py:1071-1073)",
    )
    check(
        "the grinder kept hold of the chest's own definition, which the report needs",
        G._last_chest is not None and "TreasureChest_Golden" in str(G._last_chest),
        str(G._last_chest),
    )
    check(
        "the busy flag is clear again after the menu was dismissed",
        G._busy is False,
        f"_busy={G._busy} - if this is True the menu is still on screen; dismiss it and re-run",
    )
    check(
        "this ran in the same map run 1 armed it in",
        HERE == GRINDER_CHEST_MAP,
        f"armed in {GRINDER_CHEST_MAP}, read in {HERE}",
    )

    G.diagnose.value = GRINDER_CHEST_DIAGNOSE
    del GRINDER_CHEST_MARK
    print(f"\ndiagnostic logging back to {GRINDER_CHEST_DIAGNOSE}; run this file again to re-arm.")

except Exception:  # noqa: BLE001 - a raise must not cost the scoreboard
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

summary()
