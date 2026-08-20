# Game feel across a map change - the half of AUDIT-RAW/game-feel-configtweaks.md claim 3
# that only a level load can answer: whether the two live values survive one.
#
# Nothing here waits. It runs TWICE and leaves itself a note in between, because the wait has
# to be done by the shell - a poll loop inside a request holds the very thread the map change
# needs and deadlocks the game.
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/game-feel-and-files-needs-travel.py
#        reads the map and the two live values, prints them, starts fast travel, returns.
#
#   2. wait OUTSIDE, until the map name it printed is no longer the current one:
#        for i in $(seq 40); do sleep 3; \
#          echo 'print(where())' | bash bl2-mcp/tools/ask.sh; done
#      (the bridge stops answering for several seconds mid-load; that is loading, not death.)
#
#   3. ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh \
#        bl2-mcp/tools/checks/game-feel-and-files-needs-travel.py
#        same file again: it finds its own note and reports.
#
# Why it is worth the two trips: nothing re-applies these on a level load. core.py's
# on_character_live re-runs the patch's hotfix commands and nothing else, and apply_all is
# wired to the main menu (core.py:436-468) and to a character load (__init__.py:39). If the
# console `set` only reached the player controller that was alive at the time, a fresh one
# spawned by the next map would come back with the game's own defaults and the shake returns.

reset()

if "GAMEFEEL_BEFORE" not in globals():
    GAMEFEEL_BEFORE = None


def _peek(get):
    try:
        return True, get()
    except Exception as ex:  # noqa: BLE001
        return False, repr(ex)


p = pc()
_, shake = _peek(lambda: p.bLandingShake)
_, smoothing = _peek(lambda: p.PlayerInput.bEnableMouseSmoothing)
here = where()

if GAMEFEEL_BEFORE is None:
    # --- step 1: read, remember, leave ------------------------------------------------------
    check(
        "landing camera shake is off before the map change, so there is something to lose",
        shake in (False, 0),
        f"pc.bLandingShake = {shake!r} in {here}",
    )
    check(
        "mouse smoothing is off before the map change",
        smoothing in (False, 0),
        f"pc.PlayerInput.bEnableMouseSmoothing = {smoothing!r}",
    )

    # Somewhere that is not here. Station names are the game's own, so they are read rather
    # than guessed, and anything naming the current map is skipped or the load never happens.
    elsewhere = [name for name in sorted(stations()) if here.lower() not in name.lower()]
    target = next((n for n in elsewhere if "sanctuary" in n.lower()), elsewhere[0] if elsewhere else None)
    check(
        "there is a fast travel station to leave for",
        target is not None,
        f"{len(elsewhere)} stations that are not {here}",
    )

    GAMEFEEL_BEFORE = {"map": here, "shake": shake, "smoothing": smoothing, "target": target}
    if target:
        travel_to(target)
    print(f"\nSTEP 1 of 2. Leaving {here} for {target}.")
    print("Wait for where() to stop saying " + here + ", then run this same file again.")

else:
    # --- step 3: the same two values, one map later -----------------------------------------
    before = GAMEFEEL_BEFORE
    GAMEFEEL_BEFORE = None  # so the file can be run again from the top afterwards

    # First, and most importantly: this run is only worth anything if the map really changed.
    # Without this the whole file passes by never having left, which is the failure mode the
    # audit's own "proven today" column is full of.
    check(
        "the map really changed, so the two checks below are measuring a level load",
        here.lower() != before["map"].lower(),
        f"{before['map']} -> {here} (asked for {before['target']})",
    )
    check(
        "landing camera shake is still off after a map change",
        shake in (False, 0),
        f"pc.bLandingShake was {before['shake']!r} in {before['map']}, is {shake!r} in {here}",
    )
    check(
        "mouse smoothing is still off after a map change",
        smoothing in (False, 0),
        f"bEnableMouseSmoothing was {before['smoothing']!r}, is {smoothing!r}",
    )
    print(f"\nSTEP 2 of 2. {before['map']} -> {here}.")

summary()
