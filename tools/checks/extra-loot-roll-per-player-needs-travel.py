# Extra loot roll per player - the half that needs a map with something alive in it.
# Claims 3, 4, 7 and 13 of AUDIT-RAW/extra-loot-roll-per-player.md.
#
# THE SEQUENCE THE OPERATOR RUNS, from the game folder. Nothing here waits: the waiting is the
# shell's job, because a wait inside a bridge request freezes the frame the request is running in.
#
#   bash bl2-mcp/tools/cycle.sh                                  # fresh game, character in the world
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py           # harness into that same session
#   echo 'print(sorted(stations()))' | bash bl2-mcp/tools/ask.sh # what this character can reach
#   echo 'print(travel_to("Lynchwood"))' | bash bl2-mcp/tools/ask.sh   # returns immediately
#   sleep 60
#   echo 'print(where(), len([p for p in find_actor("WillowAIPawn") if p.Health > 0]))' \
#        | ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh              # repeat until it says Lynchwood
#                                                                # AND a non-zero count
#   ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh \
#        bl2-mcp/tools/checks/extra-loot-roll-per-player-needs-travel.py
#
# Any map with living enemies will do; Lynchwood is named because stress-travel.sh already goes
# there. Do NOT run it in Sanctuary - there is nothing there to take loot off, and every check
# below will fail for that reason and no other. For the last check (a boss's guaranteed unique
# drop) travel somewhere with a named boss instead.
#
# What it leaves behind: pickups on the floor around two or three enemies that did not die. They
# are harmless and go with the map. Nothing of the player's is touched, and nothing is consumed.
reset()

from collections import Counter

import unrealsdk
from bl2_modern.features import extraloot as X

was_enabled = X.enabled.value
was_rolls = X.rolls_each.value
real_player_count = X._player_count


def pickup_names():
    """Every pickup lying in the world, by name. Names, not objects, so nothing has to be hashed."""
    out = []
    for p in unrealsdk.find_all("WillowPickup"):
        if str(p.Name).startswith("Default__"):
            continue
        try:
            out.append(str(p.Inventory.GetShortHumanReadableName()))
        except Exception as ex:  # noqa: BLE001 - an empty pickup still counts as one pickup
            out.append(f"<unnamed: {ex.__class__.__name__}>")
    return out


def drop(pawn):
    """
    Ask one enemy to roll its loot, and hand back the names of what appeared.

    DropLootOnDeath takes (Killer, DamageType, DamageTypeDefinition) - decompiled and recorded in
    BL2-COOP-CORRECTIONS.md:17. Whether pyunrealsdk will fill those in for us is exactly the sort
    of thing to measure rather than assume, so both forms are tried and the one that worked is
    reported.
    """
    before = Counter(pickup_names())
    form = ""
    problem = ""
    for label, args in (
        ("DropLootOnDeath()", ()),
        ("DropLootOnDeath(None, None, None)", (None, None, None)),
    ):
        try:
            pawn.DropLootOnDeath(*args)
            form = label
            break
        except Exception as ex:  # noqa: BLE001, PERF203 - the signature is what is being probed
            problem = f"{label} -> {ex!r}"
    after = Counter(pickup_names())
    return list((after - before).elements()), (form or f"REFUSED: {problem}")


def is_champion(pawn):
    try:
        return bool(pawn.IsChampion())
    except Exception:  # noqa: BLE001
        return "badass" in str(pawn.Name).lower()


try:
    alive = [p for p in find_actor("WillowAIPawn") if getattr(p, "Health", 0) > 0]
    check(
        "there are living enemies here to take loot from",
        len(alive) >= 2,
        f"{len(alive)} alive in {where()} - this file needs at least two",
    )

    if len(alive) >= 2:
        # --- does the mechanism the whole feature rests on work at all ------------------------
        X.enabled.value = False
        X._player_count = real_player_count
        first, form = drop(alive[0])
        check(
            "the game accepts a hand-made call to DropLootOnDeath",
            not form.startswith("REFUSED"),
            form,
        )
        check(
            "an enemy asked to drop its loot actually drops some, with the feature switched off",
            len(first) > 0,
            f"{len(first)} pickups from {alive[0].Name}: {first} - if this is 0 every number "
            f"below it is meaningless",
        )
        second, _ = drop(alive[0])
        check(
            "asking the same enemy a second time drops loot again - the feature is only re-calling",
            len(second) > 0,
            f"{len(second)} more pickups from the same enemy: {second}",
        )

        # --- claims 3 and 7: the same enemy, with the feature off and then on -----------------
        # Same pawn both times, so the pool is the same one; different pawns would be comparing
        # two different loot tables and calling the difference a result.
        control, _ = drop(alive[1])
        X.enabled.value = True
        X._player_count = lambda: 2
        X.rolls_each.value = 5
        boosted, _ = drop(alive[1])
        faked = (
            "the player count is FAKED to 2 here, so this measures the code path and not real co-op"
        )
        check(
            "with the feature on the same enemy leaves more on the floor than it did with it off",
            len(boosted) > len(control),
            f"off: {len(control)} {control}; on at 5 rolls each: {len(boosted)} {boosted} - {faked}",
        )
        check(
            "turning the feature on never costs the enemy its own drop",
            len(boosted) >= len(control),
            f"{len(control)} with it off, {len(boosted)} with it on - {faked}",
        )
        check(
            "the extra rolls are independent - they do not all come back as the same item",
            len(boosted) >= 2 and len(set(boosted)) > 1,
            f"{len(boosted)} pickups, {len(set(boosted))} of them distinct: {boosted}",
        )
        check(
            "the feature did not switch itself off while doing all that",
            X.enabled.value is True,
            f"enabled.value = {X.enabled.value} - False means a roll raised and the log says why",
        )

        # --- claim 13: a guaranteed unique, rolled twice --------------------------------------
        # "No duplicates at all" would be the wrong test - two white pistols out of one pool is
        # ordinary luck, not a bug. The signature of a doubled GUARANTEED drop is narrower: an item
        # the champion drops on its own, appearing more than once as soon as the feature is on. So
        # the champion is asked twice, once each way, and only names present in both runs count.
        used = alive[:2]
        spare = [p for p in alive if is_champion(p) and not any(p is u for u in used)]
        champions = spare or [p for p in alive if is_champion(p)]
        if champions:
            champ = champions[0]
            X.enabled.value = False
            X._player_count = real_player_count
            plain, _ = drop(champ)
            X.enabled.value = True
            X._player_count = lambda: 2
            X.rolls_each.value = 1
            doubled, _ = drop(champ)
            repeated = sorted({name for name in plain if doubled.count(name) > 1})
            check(
                "a champion's guaranteed drop is not handed out twice",
                not repeated,
                f"{champ.Name} on its own dropped {plain}; with one extra player it dropped "
                f"{doubled}; {repeated or 'nothing'} came out of both and more than once. {faked}. "
                f"Only conclusive on a boss whose unique drop is guaranteed - an ordinary badass "
                f"repeating a white gun is luck",
            )
        else:
            check(
                "there is a champion here to test the guaranteed-drop claim on",
                False,
                f"none among {len(alive)} enemies in {where()} - re-run this file on a boss map",
            )
    else:
        print("!!! skipped every drop check: nothing alive here to take loot from")

finally:
    X._player_count = real_player_count
    X.enabled.value = was_enabled
    X.rolls_each.value = was_rolls
    X._rolling = False
    check(
        "everything this file changed has been put back",
        X.enabled.value == was_enabled
        and X.rolls_each.value == was_rolls
        and X._player_count is real_player_count
        and X._rolling is False,
        f"enabled={X.enabled.value} rolls={X.rolls_each.value} _rolling={X._rolling}",
    )

summary()
