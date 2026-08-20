# Core map watcher - the claims in AUDIT-RAW/core-registry-options-patch-timing-map-w.md that
# need a map change: claim 6 (map-specific commands run when their map loads), the level-load
# half of the timing claims, and the one-shot map-name bug.
#
# It is one file run TWICE, either side of a fast travel. The first run leaves a baseline in the
# bridge's scope; the second compares against it and then refreshes the baseline, so you can
# travel and re-run as many times as you like.
#
# THE SEQUENCE, from the shell - never poll from inside a request, because the map change needs
# the very frame a loop would be holding:
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/core-and-registry-needs-travel.py
#        -> prints the baseline and the map names the patch actually holds commands for.
#           Pick a destination whose map is on that list, or claim 6 cannot be checked.
#
#   2. echo 'travel_to("Frostburn Canyon")' | bash bl2-mcp/tools/ask.sh
#        -> returns immediately. Use stations() from step 1's output to get the exact name.
#
#   3. sleep 20; then poll from the shell until the name changes:
#        until [ "$(echo 'print(where())' | ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh)" != "<old>" ];
#        do sleep 5; done
#
#   4. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/core-and-registry-needs-travel.py
#        -> the checks.
#
# The other half of claim 6 is a log line, and it is checked by
# core-and-registry-files.py ("map-specific commands ran when their map loaded").
# Same for the bridge's _ready race, which only shows up as a second 'bridge: watching' line.

from bl2_modern import core
from bl2_modern.features import bridge

_now = {
    "map": where(),
    "map_done": core._map_done,
    "ticks": core._tick_count,
    "served": bridge._served,
    "held": sum(len(v) for v in core._by_level.values()),
    "repeat": len(core._repeat_on_level_load),
}

if "CORE_TRAVEL_BASELINE" not in globals():
    CORE_TRAVEL_BASELINE = _now
    print(f"baseline taken here: {_now}")
    print()
    print("maps the patch holds commands for - travel to one of these:")
    print(sorted(core._by_level))
    print()
    print("fast travel station names:")
    print(sorted(stations()))
    print()
    print("now travel, wait for where() to change, and run this file again.")
else:
    reset()
    _was = CORE_TRAVEL_BASELINE

    check(
        "the map really did change between the two runs",
        _now["map"] != _was["map"],
        f"{_was['map']} -> {_now['map']}",
    )
    check(
        "the map watcher noticed the new map, on its own, without being asked",
        _now["map_done"] not in (None, _was["map_done"]),
        f"_map_done {_was['map_done']} -> {_now['map_done']}",
    )
    check(
        "the name the watcher settled on is the name the game gives the map, or the name the patch gives it",
        _now["map_done"] == _now["map"].lower() or _now["map_done"] in core._by_level,
        f"_map_done={_now['map_done']}, GetMapName={_now['map'].lower()}, "
        f"in the patch: {_now['map_done'] in core._by_level}",
    )
    check(
        "the watcher's tick counter advanced, so it is still being called every frame",
        _now["ticks"] > _was["ticks"],
        f"{_was['ticks']} -> {_now['ticks']} ticks",
    )

    # Claim 6 itself. It can only be checked at a destination the patch has commands for -
    # if this fails on "not one of the maps", travel somewhere from the list step 1 printed.
    _here = _now["map"].lower()
    check(
        "this map is one the patch holds commands for, so its arrival is worth checking",
        _here in core._by_level,
        f"{_here}: {len(core._by_level.get(_here, []))} commands held for it"
        if _here in core._by_level
        else f"{_here} is not in the patch - travel to one of {sorted(core._by_level)[:8]}...",
    )
    if _here in core._by_level:
        check(
            "arriving here made the watcher run this map's commands and remember it had",
            _now["map_done"] == _here and len(core._by_level[_here]) > 0,
            f"{len(core._by_level[_here])} commands for {_here}, watcher says {_now['map_done']}",
        )

    # Running a map's commands must not consume them: leave and come back and they have to run
    # again, because a level load undoes a plain set.
    check(
        "running a map's commands did not empty the list, so coming back here will run them again",
        _now["held"] == _was["held"] and all(v for v in core._by_level.values()),
        f"{_was['held']} -> {_now['held']} commands held in total",
    )
    check(
        "the run-on-every-level-load list was not extended by the arrival",
        _now["repeat"] == _was["repeat"],
        f"{_was['repeat']} -> {_now['repeat']} commands repeating on each level load",
    )

    # The bug: _logged_map_name is one bool for the whole process, and the menu map always gets
    # there first, so no real map's name is ever reported however many times you travel. This
    # check passes while the bug is present; the fix is a set of names, and then it fails.
    check(
        "the map-name report is still stuck on the main menu, however many maps have loaded since",
        core._logged_map_name is True,
        "no new 'the game calls this map' line can appear - grep unrealsdk.log to confirm",
    )

    CORE_TRAVEL_BASELINE = _now
    summary()
    print("\nbaseline refreshed - travel again and re-run to check another arrival.")
