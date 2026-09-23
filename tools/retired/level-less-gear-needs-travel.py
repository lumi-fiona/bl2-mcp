# Level-less gear - the two claims that need a character load (audit claims 12 and 14)
#
# This file is run TWICE around a character reload. It arms itself the first time and reports
# the second time, deciding which by whether the witness list is already on the module.
#
# OPERATOR SEQUENCE - the waiting is all yours, nothing in here sleeps or polls:
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   2. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/level-less-gear-needs-travel.py
#        -> prints "ARMED". It has put a probe id in the marked list and saved the character.
#   3. Save and quit to the main menu, load a DIFFERENT character, then load this one back.
#      (mcp__bl2__game_load_character does this, and it steals the keyboard, so a person has
#      to be at the machine. Loading a second character in between is what proves the list is
#      per-character rather than a machine-wide leftover.)
#   4. Wait until the map has finished loading. Poll it from the shell, never from in here:
#        bash bl2-mcp/tools/ask.sh <(echo 'print(where(), level())')
#      Repeat until it prints the map you loaded into.
#   5. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   6. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/level-less-gear-needs-travel.py
#        -> prints the PASS/FAIL lines and puts everything back.
#
# If you abandon the run half way, this one line disarms it:
#   bash bl2-mcp/tools/ask.sh <(echo 'from bl2_modern.features import levelless as L
#   L.relevel_all = L._real_relevel_all; L._forget(987654321); del L._witness, L._real_relevel_all')

from bl2_modern.features import levelless as L

# An id no item carries. The list is what is being tested, not any particular gun, and a probe
# id that matches nothing means relevel_all can never rebuild real gear off the back of it.
PROBE = 987654321

if not hasattr(L, "_witness"):
    # ---------------- ARM ----------------------------------------------------------------
    reset()
    L._witness = []
    L._real_relevel_all = L.relevel_all

    # on_character_live calls the module-global relevel_all, so replacing that global does
    # intercept the live hook. Replacing on_character_live.__wrapped__ would NOT: mods_base
    # hands the original function to add_hook at enable time (mods_base/hook.py:39), so the
    # game keeps calling the function object it was given, whatever the attribute says later.
    # Everything it needs comes off the controller it was handed, not off harness globals -
    # this runs inside a game hook during a load, and a NameError there would break the load
    # rather than fail a check.
    def _witnessed(controller):
        try:
            where_now = str(controller.WorldInfo.GetMapName(False))
        except Exception as ex:
            where_now = repr(ex)
        L._witness.append((sorted(L._ids()), L._player_level(controller), where_now))
        return L._real_relevel_all(controller)

    L.relevel_all = _witnessed

    L._remember(PROBE)
    check(
        "the probe id is in the marked list before saving",
        PROBE in L._ids(),
        f"marked.value = {list(L.marked.value)}",
    )
    pc().SaveGame()
    print(
        f"ARMED: probe {PROBE} remembered and the character saved, at {where()} level {level()}.\n"
        f"Now load another character, load this one back, wait for the map, and run this file "
        f"again."
    )
    summary()

else:
    # ---------------- REPORT -------------------------------------------------------------
    reset()
    seen = list(L._witness)
    try:
        check(
            "the marked list survived a character load",
            PROBE in L._ids(),
            f"marked.value = {list(L.marked.value)}; if this is empty the LoadGame hook "
            f"(save_options/hooks.py:130) reset it and EndLoadGame never put it back",
        )
        check(
            "relevel_all ran at least once while the character was coming back",
            bool(seen),
            f"{len(seen)} calls recorded: {seen}",
        )
        # Claim 14. save_options fills the option on WillowSaveGameManager:EndLoadGame POST;
        # levelless reads it on WillowPlayerController:SpawningProcessComplete. Nothing orders
        # those two. If the first call saw an empty list, levelless ran first and the catch-up
        # on load is a no-op every single time.
        check(
            "the first call after loading already saw a populated list",
            bool(seen) and bool(seen[0][0]),
            f"first call saw ids {seen[0][0] if seen else 'nothing - it never ran'} at level "
            f"{seen[0][1] if seen else '?'} in {seen[0][2] if seen else '?'}",
        )
        check(
            "the level it saw on load is the character's real level",
            bool(seen) and seen[0][1] == level(),
            f"saw {seen[0][1] if seen else '?'}, character is {level()}",
        )
    finally:
        L.relevel_all = L._real_relevel_all
        L._forget(PROBE)
        del L._witness
        del L._real_relevel_all
        pc().SaveGame()
        print(f"disarmed: relevel_all restored, probe forgotten, marked.value={list(L.marked.value)}")
    summary()
