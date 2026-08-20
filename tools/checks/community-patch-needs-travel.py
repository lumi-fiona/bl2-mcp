# Community Patch - the one claim that needs a map change (AUDIT-RAW/community-patch.md, claim 6)
#
# The counts are proved on disk by community-patch-files.py. What no file can prove is DELIVERY:
# that when a map with held commands loads, the tick watcher notices and hands that map's
# commands to the console. This file proves it, in two runs, on whatever map you are standing in.
#
# THE SEQUENCE THE OPERATOR RUNS (nothing here waits, so the waiting is the shell's job):
#
#   1. see what stations exist:
#        echo 'print(sorted(stations()))' | bash bl2-mcp/tools/ask.sh
#   2. go somewhere. Any map with held commands will do; run 1 below names some if you land badly:
#        echo 'print(travel_to("Tundra Express"))' | bash bl2-mcp/tools/ask.sh
#   3. wait for the load - it takes tens of seconds and the bridge stops answering during it:
#        sleep 20; ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh <<< 'print(where())'
#      repeat until the name changes.
#   4. re-send the harness (a map change does not clear it, but a relaunch does):
#        bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   5. RUN 1 - checks the arrival, then arms the re-delivery test:
#        bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/community-patch-needs-travel.py
#   6. wait two seconds. The watcher samples every 30th frame, so this is generous:
#        sleep 2
#   7. RUN 2 - same file, same map. It sees the armed state and checks what the watcher did:
#        bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/community-patch-needs-travel.py
#
# Run 1 wraps core._run rather than replacing it: the wrapper records and then calls the real
# thing, so if you abandon the sequence after run 1 nothing is broken - the only residue is a
# growing list. To clear it by hand:
#   echo 'from bl2_modern import core; core._run = core._check_cp_travel["real"]; del core._check_cp_travel' | bash bl2-mcp/tools/ask.sh
reset()

import unrealsdk

from bl2_modern import core

SENTINEL = "123456"

controller = pc()
here = core._current_map(controller)
held = list(core._by_level.get(here or "", []))
armed = getattr(core, "_check_cp_travel", None)

if armed is None:
    # ---------------------------------------------------------------- RUN 1: arrival, then arm
    check(
        "the game is in a real map, not the menu",
        here is not None and here not in ("menumap", "loader"),
        f"the map reads as {here!r}, where() says {where()!r}",
    )
    check(
        "this map is one the patch holds commands for",
        bool(held),
        f"{len(held)} commands held for {here!r}."
        + ("" if held else f" Try one of: {sorted(core._by_level)[:12]}"),
    )
    check(
        "the watcher matched this map when it loaded, so its commands have already run once",
        core._map_done == here,
        f"_map_done={core._map_done!r}, this map is {here!r}",
    )

    # The commands this map holds, landing on real objects. Same sentinel sandwich as the main
    # file: write 123456, confirm it moved, run the patch's own line, confirm it moved back. Only
    # plain-identifier properties holding a bare number are touched, so every one can be written
    # back exactly. Not every map has any - 25 of the 80 do - so the count is checked as well.
    pool = []
    for command in held:
        parts = command.split(None, 3)
        if len(parts) != 4 or parts[0].lower() != "set":
            continue
        _set, path, prop, want = parts
        want = want.strip()
        if not prop.isidentifier():
            continue
        try:
            float(want)
        except ValueError:
            continue
        pool.append((path, prop, want))

    touched = []
    usable = landed = inert = unresolved = 0
    misses = []
    try:
        for path, prop, want in pool:
            try:
                obj = unrealsdk.find_object("Object", path)
                before = str(getattr(obj, prop))
                float(before)
            except Exception:  # noqa: BLE001 - not loaded, or not a number: no answer either way
                unresolved += 1
                continue
            touched.append((path, prop, before))
            controller.ConsoleCommand(f"set {path} {prop} {SENTINEL}")
            mid = str(getattr(obj, prop))
            if mid == before:
                continue  # the sentinel never landed, so this target can say nothing
            usable += 1
            controller.ConsoleCommand(f"set {path} {prop} {want}")
            after = str(getattr(obj, prop))
            if after == mid:
                inert += 1
                if len(misses) < 6:
                    misses.append((path, prop, before, after))
            else:
                landed += 1
    finally:
        for path, prop, original in touched:
            try:
                controller.ConsoleCommand(f"set {path} {prop} {original}")
            except Exception as ex:  # noqa: BLE001 - keep restoring the rest
                print(f"   could not restore {path} {prop} to {original}: {ex!r}")

    if pool:
        check(
            "this map's own held commands really do change the objects they name",
            usable > 0 and inert == 0,
            f"{landed} landed, {inert} did nothing, {usable} usable of {len(pool)} numeric"
            f" targets ({unresolved} objects not loaded); misses: {misses}",
        )
    else:
        # Honest gap rather than a check that cannot fail: 55 of the 80 held maps write only
        # structs, arrays and object references, none of which can be written back exactly.
        print(
            f"   NOT CHECKED: none of {here!r}'s {len(held)} held commands writes a plain number,"
            " so there is nothing here that can be clobbered and restored safely.",
        )

    real_run = core._run
    seen = []

    def recording_run(commands, _real=real_run, _seen=seen):
        """Records what the watcher hands over, then runs it for real."""
        _seen.extend(commands)
        return _real(commands)

    core._run = recording_run
    core._check_cp_travel = {"real": real_run, "seen": seen, "map": here, "held": held}
    # Making the watcher believe it has not seen this map yet. On its next 30th frame it should
    # notice the map, match it, and hand this map's commands to _run - which is now the recorder.
    core._map_done = None
    print(
        f"\nARMED on {here!r} ({len(held)} held commands). Wait two seconds, then run this file"
        " again to see what the watcher did.",
    )

else:
    # ---------------------------------------------------------------- RUN 2: what the watcher did
    seen = armed["seen"]
    was = armed["map"]
    expected = armed["held"]
    try:
        check(
            "you are still in the map that was armed",
            here == was,
            f"armed on {was!r}, now in {here!r}",
        )
        check(
            "the watcher noticed the map again and ran something",
            bool(seen),
            f"{len(seen)} commands passed to _run since arming"
            + ("" if seen else " - give it another second and run this file again"),
        )
        check(
            "what the watcher handed over is exactly this map's held commands, and nothing else",
            seen == expected,
            f"{len(seen)} commands delivered, {len(expected)} held;"
            f" first difference: {next((f'{a[:70]!r} vs {b[:70]!r}' for a, b in zip(seen, expected) if a != b), 'none')}",
        )
        check(
            "the watcher marked the map done again, so it will not run them once a frame",
            core._map_done == was,
            f"_map_done={core._map_done!r}, armed map was {was!r}",
        )
    finally:
        core._run = armed["real"]
        del core._check_cp_travel

summary()
