# The night's log - the four claims that need something to actually happen.
#
# Nothing in this file sleeps or polls. It is run TWICE, and the waiting is all yours. It decides
# which run it is by whether it has already left a marker on the module.
#
# OPERATOR SEQUENCE
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   2. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/the-nights-log-needs-travel.py
#        -> prints "ARMED" and the name of the file it will read afterwards.
#   3. NOW GO AND PLAY, for two or three minutes, and do all four of these:
#        - kill at least ten things
#        - pick up at least one gun off the floor
#        - travel to a different map (fast travel is fine)
#        - go down once on purpose, then get a second wind or bleed out
#   4. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   5. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/the-nights-log-needs-travel.py
#        -> prints the PASS/FAIL lines.
#
# If you abandon it half way, this one line disarms it:
#   bash bl2-mcp/tools/ask.sh <(echo 'from bl2_modern.features import nightlog as N; del N._armed')
#
# WHAT THIS CAN AND CANNOT PROVE. It proves the hooks fire in a real game, which is the whole
# unverified half of the feature. It cannot prove anything about a second player - drops and kills
# happen on the host, so a guest's file being empty is correct and this file would call it a
# failure. Run it on the host.

from bl2_modern.features import nightlog as N

if not hasattr(N, "_armed"):
    # ---------------- ARM ----------------------------------------------------------------
    reset()
    N._armed = {
        "shapes": dict(N._shape_seen),
        "file": N._file,
    }
    # Force a fresh file so the counting starts from zero rather than from whatever the evening
    # already contained. The old file is left alone on disk.
    N._file = None
    N._bytes = 0
    N.enabled.value = True
    N._writing_broken = False
    del N._pending[:]
    N._flush()
    N._armed["file"] = N._file
    print(f"ARMED. Now go and play. Afterwards this will read {N._file}")
    print("Do all four: kill ten things, pick up a gun, change map, go down once.")

else:
    # ---------------- REPORT -------------------------------------------------------------
    reset()
    import json

    armed = N._armed
    N._flush()
    path = N._file or armed["file"]

    lines = []
    for candidate in sorted(path.parent.glob(path.name.split("-part")[0].removesuffix(".jsonl") + "*")):
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    lines.append(json.loads(line))
                except Exception:
                    pass

    def count(kind):
        return len([e for e in lines if e.get("kind") == kind])

    check(
        "a file was written and it parses",
        len(lines) > 0,
        f"{len(lines)} events in {path}",
    )
    check(
        "the first line records whether this machine can see kills at all",
        lines and lines[0].get("kind") == "night began",
        f"{lines[0] if lines else '(nothing)'}",
    )
    check(
        "this was run on the host, so kills and drops are expected to be in here",
        lines and lines[0].get("on_the_host") is True,
        "if this fails, every check below is failing for the right reason and the feature is fine",
    )

    check(
        "killing things really is recorded - the AwardCombatExperience hook fires in a real game",
        count("killed") >= 10,
        f"{count('killed')} kills recorded, ten asked for",
    )
    timed = [
        e for e in lines
        if e.get("kind") == "killed" and isinstance(e.get("took_seconds"), (int, float))
    ]
    check(
        "at least some kills came with a time, so the TakeDamage hook fires too",
        len(timed) >= 3,
        f"{len(timed)} of {count('killed')} kills carry a time. Zero means neither "
        f"WillowPawn:TakeDamage nor Engine.Pawn:TakeDamage is the right function",
    )
    check(
        "those times are plausible seconds rather than nonsense",
        all(0.0 < e["took_seconds"] < 600 for e in timed),
        f"{sorted(e['took_seconds'] for e in timed)[:12]}",
    )
    check(
        "each kill says who did it, rather than 'someone'",
        count("killed") and all(
            e.get("by") not in (None, "someone")
            for e in lines if e.get("kind") == "killed"
        ),
        f"{sorted({e.get('by') for e in lines if e.get('kind') == 'killed'})}",
    )
    check(
        "each kill says what died, rather than 'something'",
        count("killed") and len({
            e.get("what") for e in lines if e.get("kind") == "killed"
        } - {"something", None}) >= 1,
        f"{sorted({e.get('what') for e in lines if e.get('kind') == 'killed'})[:10]}",
    )

    check(
        "enemies dropping loot is recorded - the DropLootOnDeath hook fires",
        count("dropped") >= 1,
        f"{count('dropped')} drops recorded",
    )
    check(
        "picking a gun up is recorded - PickupPickupable is the right guess",
        count("picked up") >= 1,
        f"{count('picked up')} pickups. Zero here with drops above is the answer to "
        f"'is PickupPickupable the function a person pressing E goes through' - it is not, "
        f"and TouchedPickupable is the next candidate",
    )
    check(
        "a pickup says who took it and what it was",
        all(
            e.get("by") not in (None, "someone") and e.get("what") not in (None, "something")
            for e in lines if e.get("kind") == "picked up"
        ),
        f"{[(e.get('by'), e.get('what')) for e in lines if e.get('kind') == 'picked up'][:8]}",
    )

    check(
        "changing map is recorded, and not as 'loader'",
        count("arrived") >= 1
        and all(
            str(e.get("where", "")).lower() != "loader"
            for e in lines if e.get("kind") == "arrived"
        ),
        f"{[e.get('where') for e in lines if e.get('kind') == 'arrived']}",
    )
    check(
        "going down is recorded - one of the two guessed injured-state functions is real",
        count("went down") >= 1,
        f"{count('went down')} downs. Zero means neither SetupPlayerInjuredState nor "
        f"SetInjuredState is a hookable function on WillowPlayerPawn",
    )

    check(
        "which spellings actually fired, for the record",
        bool(N._shape_seen),
        f"{N._shape_seen}",
    )

    del N._armed
    check(
        "the marker is gone, so this file can be run again from the start",
        not hasattr(N, "_armed"),
        "disarmed",
    )

    summary()
