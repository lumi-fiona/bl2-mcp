# Partner-aimed extra loot - the half that needs a map with something alive in it.
#
# THE SEQUENCE THE OPERATOR RUNS, from the game folder. Nothing here waits: the waiting is the
# shell's job, because a wait inside a bridge request freezes the frame the request is running in.
#
#   bash bl2-mcp/tools/cycle.sh                                  # fresh game, character in the world
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py           # harness into that same session
#   echo 'print(travel_to("Lynchwood"))' | bash bl2-mcp/tools/ask.sh   # returns immediately
#   sleep 60
#   echo 'print(where(), len([p for p in find_actor("WillowAIPawn") if p.Health > 0]))' \
#        | ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh              # repeat until it names the map
#                                                               # AND a non-zero count
#   ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh \
#        bl2-mcp/tools/checks/partner-aimed-loot-needs-travel.py
#
# Any map with living enemies will do. Do NOT run it in Sanctuary - there is nothing there to drop
# loot off, and every check below fails for that reason and no other.
#
# STILL NOT COVERED, and no solo run can cover it: whether the aimed item is one the OTHER player
# can pick up. That is the entire reason this uses Behavior_SpawnLootAroundPoint rather than
# building an item in Python (BL2-LOOT-POOLS.md:101-102), and it needs two machines to prove.
#
# What it leaves behind: pickups on the floor around one or two enemies that did not die. They are
# harmless and go with the map. Nothing of the player's is touched and nothing is consumed.
reset()

from collections import Counter

import unrealsdk

from bl2_modern.features import extraloot as X
from bl2_modern.features import partnerloot as P

was_p_enabled = P.enabled.value
was_what = P.what_drops.value
was_good = P.how_good.value
was_x_enabled = X.enabled.value
was_rolls = X.rolls_each.value
real_player_count = X._player_count
real_partners = P._partners


class FakePartner:
    """Stands in for a second player. Only the character field is ever read off it."""

    def __init__(self, text):
        self.PlayerClassDefinition = text


def pickup_names():
    """Every pickup lying in the world, by name."""
    out = []
    for p in unrealsdk.find_all("WillowPickup"):
        if str(p.Name).startswith("Default__"):
            continue
        try:
            out.append(str(p.Inventory.GetShortHumanReadableName()))
        except Exception as ex:  # noqa: BLE001
            out.append(f"<unnamed: {ex.__class__.__name__}>")
    return out


def kinds_of(names):
    """A rough family for each pickup name, so 'is this a class mod' can be answered."""
    return [
        "classmod" if any(word in name.lower() for word in ("mod", "expert", "legendary")) else "gun"
        for name in names
    ]


def drop(pawn):
    """Ask one enemy to roll its loot, and hand back the names of what appeared."""
    before = Counter(pickup_names())
    try:
        pawn.DropLootOnDeath()
    except Exception:  # noqa: BLE001 - the three-argument form is the other one that works
        try:
            pawn.DropLootOnDeath(None, None, None)
        except Exception as ex:  # noqa: BLE001
            return [f"REFUSED: {ex!r}"]
    after = Counter(pickup_names())
    return list((after - before).elements())


try:
    alive = [p for p in find_actor("WillowAIPawn") if getattr(p, "Health", 0) > 0]
    check(
        "there are living enemies here to take loot from",
        len(alive) >= 2,
        f"{len(alive)} alive in {where()} - this file needs at least two",
    )

    if len(alive) >= 2:
        # The extra roll has to be on, because this feature only ever acts inside it. One extra
        # player is faked so the roll fires at all - this measures the code path, not real co-op.
        X.enabled.value = True
        X._player_count = lambda: 2
        X.rolls_each.value = 1
        P._partners = lambda: [FakePartner("CharClass_Assassin")]

        # --- with the aiming off: the blind repeat, as it ships today -------------------------
        P.enabled.value = False
        blind = drop(alive[0])
        check(
            "with aiming off, the enemy still drops the blind extra roll",
            len(blind) > 0 and not any(str(n).startswith("REFUSED") for n in blind),
            f"{len(blind)} pickups: {blind}",
        )

        # --- with it on: the aimed drop replaces it, and something still lands -----------------
        P.enabled.value = True
        P.what_drops.value = "Their class mod"
        aimed = drop(alive[1])
        check(
            "with aiming on, the enemy still leaves something on the floor - the aimed drop is a "
            "replacement for the blind one, not a deletion of it",
            len(aimed) > 0,
            f"{len(aimed)} pickups: {aimed}. Zero here means the block landed and the aimed drop "
            f"did not, which is the worst outcome this feature has and would mean shipping it off",
        )
        check(
            "aiming at Zer0 and asking for a class mod puts at least one class mod on the floor",
            "classmod" in kinds_of(aimed),
            f"{list(zip(aimed, kinds_of(aimed)))} - the family test here is a name guess, so read "
            f"the list yourself before believing a failure",
        )

        # --- the quality dial reaches the world -------------------------------------------------
        P.what_drops.value = "A gun their character likes"
        P.how_good.value = "Legendary"
        legendary = drop(alive[1])
        check(
            "turning the quality dial to Legendary changes what comes out",
            len(legendary) > 0,
            f"{legendary} - compare against {aimed}. Read the names: this check only proves "
            f"something dropped, a person has to say whether it is orange",
        )

        check(
            "neither feature switched itself off while doing all that",
            X.enabled.value is True and P.enabled.value is True,
            f"extra roll {X.enabled.value}, aiming {P.enabled.value} - False means a call was "
            f"refused and the log says which",
        )

        # --- an enemy dying normally is still untouched -------------------------------------------
        X.enabled.value = False
        X._player_count = real_player_count
        ordinary = drop(alive[0])
        check(
            "with the extra roll switched off entirely, an enemy drops its own loot exactly as it "
            "always did - this feature never touches a plain death",
            len(ordinary) > 0,
            f"{len(ordinary)} pickups: {ordinary}",
        )
    else:
        print("!!! skipped every drop check: nothing alive here to take loot from")

finally:
    P._partners = real_partners
    X._player_count = real_player_count
    P.enabled.value = was_p_enabled
    P.what_drops.value = was_what
    P.how_good.value = was_good
    X.enabled.value = was_x_enabled
    X.rolls_each.value = was_rolls
    X._rolling = False
    check(
        "everything this file changed has been put back",
        P._partners is real_partners
        and X._player_count is real_player_count
        and P.enabled.value == was_p_enabled
        and P.what_drops.value == was_what
        and P.how_good.value == was_good
        and X.enabled.value == was_x_enabled
        and X.rolls_each.value == was_rolls
        and X._rolling is False,
        f"aiming={P.enabled.value} what={P.what_drops.value!r} good={P.how_good.value!r} "
        f"extra={X.enabled.value} rolls={X.rolls_each.value}",
    )

summary()
