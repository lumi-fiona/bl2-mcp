# Small things fly to you - the half that needs real things lying on the floor
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/small-things-vacuum-needs-travel.py
#
# THIS FILE IS SEVERAL REQUESTS, NOT ONE, and one of the steps is a person shooting things. A
# bridge request that waits freezes the game - see the note at the top of harness.py - so the
# waiting is done by the shell between sends.
#
# THE SEQUENCE:
#
#   STEP 1  this file with STEP = 1   - reports what is on the floor right now, and how far away
#   STEP 2  A PERSON kills something that drops ammo and money, stands about ten metres off, and
#           does not walk towards it
#   STEP 3  this file with STEP = 3   - one real sweep, then a report of what went and what
#                                       stayed. THIS TAKES REAL ITEMS INTO THE REAL BACKPACK.
#                                       That is the point; it cannot be undone, and it only ever
#                                       takes ammo, money, eridium, vials and boosters.
#
# WHY A PERSON. Nothing here can make an enemy drop loot on demand without spawning it, and a
# spawned pickup is one this file wrote itself - which would check the feature against this
# file's idea of the world rather than against the game's.

reset()

from bl2_modern.features import vacuum as W

STEP = globals().get("STEP", 1)
p = pc()


def _floor():
    """Everything on the floor, with what the feature makes of each one."""
    out = []
    try:
        world = p.GetWillowGlobals()
        here = p.Pawn.Location
        for pickup in list(world.PickupList):
            try:
                kind, why = W._category(pickup.Inventory)
                out.append(
                    (
                        round(W._gap(here, pickup.Location)),
                        str(pickup.Inventory.Class.Name),
                        W._path_of(pickup.Inventory.DefinitionData.ItemDefinition),
                        kind or "LEFT ALONE",
                    )
                )
            except Exception as ex:
                out.append((-1, "unreadable", repr(ex), "LEFT ALONE"))
    except Exception as ex:
        print("could not read the floor: %r" % (ex,))
    return out


if STEP == 1:
    on_floor = _floor()
    check(
        "there is something on the floor to look at",
        bool(on_floor),
        "%d things in %s" % (len(on_floor), where()),
    )
    for row in on_floor[:25]:
        print("   %5s units  %-20s %-60s -> %s" % row)
    print(
        "NOW: kill something that drops ammo and money, stand about ten metres away, do NOT "
        "walk towards it, then send this file again with STEP = 3."
    )

elif STEP == 3:
    before = _floor()
    wanted = [row for row in before if row[3] != "LEFT ALONE" and row[0] <= W.distance.value]
    gear = [row for row in before if row[3] == "LEFT ALONE"]
    check(
        "there is something within reach that the vacuum should take",
        bool(wanted),
        "of %d things on the floor, %d are collectable and within %s units"
        % (len(before), len(wanted), W.distance.value),
    )

    took = W.sweep(p)
    after = _floor()

    check(
        "the sweep actually took things off the floor",
        took > 0 and len(after) < len(before),
        "it reported %d taken; the floor went from %d things to %d" % (took, len(before), len(after)),
    )
    still_there = [row for row in after if row[3] != "LEFT ALONE" and row[0] <= W.distance.value]
    check(
        "nothing collectable is still lying within reach",
        not still_there,
        "left behind: %s" % (still_there[:6],),
    )
    check(
        "everything the vacuum was told to leave alone is exactly where it was",
        len([row for row in after if row[3] == "LEFT ALONE"]) == len(gear),
        "%d things were left alone before, %d after - a drop here means a gun was taken"
        % (len(gear), len([row for row in after if row[3] == "LEFT ALONE"])),
    )
    for row in after[:25]:
        print("   %5s units  %-20s %-60s -> %s" % row)

summary()
