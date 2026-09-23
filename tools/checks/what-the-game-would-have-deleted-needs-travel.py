# What the game would have deleted - the half that only a real character load can answer.
#
# THIS FILE STILL NEVER CALLS ValidateItemDefinition OR ValidateWeaponDefinition. It waits for the
# game to call them by itself, which is the entire point: SanitySaver/hooks.py:418-419 records
# that calling them forces every item to be sanity checked and destroyed.
#
# Nothing here sleeps or polls. It is run TWICE, and the waiting is yours.
#
# OPERATOR SEQUENCE
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   2. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/what-the-game-would-have-deleted-needs-travel.py
#        -> prints "ARMED" and how many things this character is carrying right now.
#   3. Save and quit to the main menu, then load the SAME character back.
#      (mcp__bl2__game_load_character does it, and it takes the keyboard, so a person has to be
#      at the machine.)
#   4. Wait until the map has finished loading. Poll from the shell, never from in here:
#        bash bl2-mcp/tools/ask.sh <(echo 'print(where(), level())')
#   5. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   6. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/what-the-game-would-have-deleted-needs-travel.py
#        -> prints the PASS/FAIL lines.
#
# Disarm without finishing:
#   bash bl2-mcp/tools/ask.sh <(echo 'from bl2_modern.features import itemcheck as I; del I._armed')
#
# BACK YOUR SAVES UP FIRST. Nothing here writes to a save, and the pack ships savebackup.py, but
# this is the one area of the game where being wrong costs gear rather than time.

from bl2_modern.features import itemcheck as I
from bl2_modern.features.grinder import carried

if not hasattr(I, "_armed"):
    # ---------------- ARM ----------------------------------------------------------------
    reset()
    live = carried(pc())
    ids = []
    for item in live:
        try:
            ids.append(int(item.DefinitionData.UniqueId))
        except Exception:
            pass

    I._armed = {
        "carried": len(live),
        "ids": sorted(ids),
        "guns": len([i for i in live if str(i.Class.Name) == "WillowWeapon"]),
    }
    I.enabled.value = True
    print(f"ARMED. Carrying {len(live)} things ({I._armed['guns']} of them guns), "
          f"{len(ids)} with a readable id.")
    print("Now save and quit to the main menu, load this same character back, and run this again.")

else:
    # ---------------- REPORT -------------------------------------------------------------
    reset()
    armed = I._armed

    # The load handler has already run and cleared _seen, so what is being read here is the
    # report it produced, which is what a player would see.
    report = I._last_report

    check(
        "the feature produced a report for the load that just happened",
        report and "checked" in report,
        report,
    )
    check(
        "the game really did run its check during the load, and this hook saw it",
        report and not report.startswith("Nothing has been checked"),
        f"{report[:200]}. If this fails, neither ValidateItemDefinition nor "
        f"ValidateWeaponDefinition is called during a load on this install - which with Sanity "
        f"Saver on is a real possibility and is written up in itemcheck.py's own docstring",
    )

    numbers = [int(n) for n in report.split() if n.isdigit()]
    check(
        "it says how many guns and items were checked",
        len(numbers) >= 2,
        report.splitlines()[0] if report else "",
    )
    # With Sanity Saver on, the game's own two Validate functions are never called during a
    # load - Sanity Saver replaces that path entirely, which is written up in itemcheck.py's
    # own docstring and is the very reason the mod is bundled. Measured 2026-08-20 on this
    # install: carrying 23, checked 0, nothing lost. So "checked 0" WITH Sanity Saver on is
    # the install working; the count assertion only means something when Sanity Saver is off.
    if "Sanity Saver is on" in report and numbers and numbers[0] == 0:
        print(
            "[SKIP] the number of guns checked is in the same region as the number carried - "
            "Sanity Saver is on, so the game's own check never runs and 0 is correct here; "
            "the real assertion (nothing went missing) is made below",
        )
    else:
        check(
            "the number of guns checked is in the same region as the number carried",
            numbers and 0 < numbers[0] <= armed["carried"] + 20,
            f"checked {numbers[0] if numbers else '?'}, was carrying {armed['carried']} "
            f"({armed['guns']} guns) before the reload",
        )

    now = carried(pc())
    now_ids = []
    for item in now:
        try:
            now_ids.append(int(item.DefinitionData.UniqueId))
        except Exception:
            pass
    gone = sorted(set(armed["ids"]) - set(now_ids))

    check(
        "nothing actually went missing across the reload",
        not gone,
        f"{len(gone)} ids present before the reload and absent after: {gone[:20]}",
    )
    check(
        "the feature's own answer agrees with counting the backpack by hand",
        bool(gone) == ("did not survive" in report),
        f"counted {len(gone)} missing by hand; the report "
        f"{'names losses' if 'did not survive' in report else 'says nothing was lost'}",
    )

    check(
        "the report says which of Sanity Saver's two worlds this was",
        "Sanity Saver" in report,
        report,
    )

    written = sorted(I.FOLDER.glob("item-check-*.md"))
    check(
        "the details were left in a file to read properly",
        bool(written),
        f"{[p.name for p in written[-3:]]} in {I.FOLDER}",
    )

    del I._armed
    check(
        "the marker is gone, so this file can be run again from the start",
        not hasattr(I, "_armed"),
        "disarmed",
    )

    summary()
