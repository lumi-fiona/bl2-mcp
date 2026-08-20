# Grinder, the grind recipe - checks for the claims in AUDIT-RAW/grinder.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/grinder.py
#
# Covers grinder.md claims 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 24 and 38, plus claim 8
# of AUDIT-RAW/grinder-regression-harness.md ("the mixed-rarity case really is mixed").
#
# SAFETY: every item fed to _grind here was spawned by this script. The finally block removes
# anything left in the backpack that was not in it when the script started and puts the money
# back, so nothing the player already owned is ever consumed or paid for.

reset()
import unrealsdk
from bl2_modern.features import grinder as G

P = pc()
NOTES = []
KEEP = {str(i) for i in G._backpack(P)}
SAVED_HOW, SAVED_COST, SAVED_GROUND, SAVED_MONEY = (
    G.how_many.value, G.cost_per_level.value, G.loot_on_ground.value, money(P),
)

# The class default object _drop_loot writes on. Saved so this run leaves the session as it
# found it - grinder.py:838-840 assigns onto it and never restores it, which is claim 38.
CDO = unrealsdk.find_object(
    "Behavior_SpawnLootAroundPoint", "WillowGame.Default__Behavior_SpawnLootAroundPoint",
)
CDO_POOLS = list(CDO.ItemPools)
CDO_RADIUS = CDO.CircularScatterRadius

REAL_NOTE = G._note
REAL_CHARGE = G._charge
G._note = lambda message: NOTES.append(message)

RARE_WEAPONS = G.POOLS[("weapon", 3)]


def bag():
    return G._backpack(P)


def pickups():
    return {str(p) for p in unrealsdk.find_all("WillowPickup")}


def added(before):
    return [i for i in bag() if str(i) not in before]


def three_rare_weapons(stage=40, spawn=4):
    """Three freshly spawned rarity-3 weapons, or fewer if the pool misbehaved."""
    made = give(RARE_WEAPONS, stage, spawn)
    return [i for i in made if G._kind(i) == "weapon" and G._rarity(i) == 3][:3]


try:
    G.how_many.value = 3
    G.cost_per_level.value = 100
    G.loot_on_ground.value = False
    add_money(2_000_000)

    # --- the backpack path -------------------------------------------------------------
    # Two at level 30 and one at 45, so "the level of the highest item in" is a number that
    # only one of the three could have produced.
    seeded = give(RARE_WEAPONS, 30, 2) + give(RARE_WEAPONS, 45, 1)
    feed = [i for i in seeded if G._kind(i) == "weapon" and G._rarity(i) == 3][:3]
    check(
        "three rare weapons can be spawned to grind with",
        len(feed) == 3,
        f"{len(feed)} of the {len(seeded)} spawned items were rarity-3 weapons",
    )

    if len(feed) == 3:
        want_cost = G._cost(feed)
        want_stage = max(G._level(i) for i in feed)
        want_kind, want_rarity = G._kind(feed[0]), G._rarity(feed[0])
        before = {str(i) for i in bag()}
        n_before, m_before = len(before), money(P)

        G._grind(P, feed)

        made = added(before)
        spent = m_before - money(P)
        check("a grind hands back exactly one new item", len(made) == 1, f"{len(made)} new items")
        check(
            "a grind of three items leaves the backpack two items lighter",
            len(bag()) - n_before == -2,
            f"backpack moved by {len(bag()) - n_before}",
        )
        check(
            "a grind charges the levels of what went in times the cost per level",
            spent == want_cost,
            f"charged ${spent:,}, the levels say ${want_cost:,}",
        )
        if made:
            out = made[0]
            check(
                "what comes out of a grind is the same kind as what went in",
                G._kind(out) == want_kind,
                f"{G._kind(out)} out, {want_kind} in",
            )
            check(
                "what comes out of a grind is the same rarity as what went in",
                G._rarity(out) == want_rarity,
                f"rarity {G._rarity(out)} out, {want_rarity} in",
            )
            check(
                "what comes out is at the level of the highest item that went in",
                G._level(out) == want_stage,
                f"level {G._level(out)} out, highest in was {want_stage}",
            )

    # --- refusals: mixed rarity ---------------------------------------------------------
    mixed = give(RARE_WEAPONS, 40, 2) + give(G.POOLS[("weapon", 9)], 40, 1)
    check(
        "the mixed-rarity feed really does hold more than one rarity",
        len({G._rarity(i) for i in mixed}) > 1,
        sorted(G._rarity(i) for i in mixed),
    )
    n, m = len(bag()), money(P)
    G._grind(P, mixed)
    check(
        "a feed of mixed rarity is refused and neither items nor money are taken",
        len(bag()) == n and money(P) == m,
        f"backpack {len(bag()) - n}, money {money(P) - m}",
    )

    # --- refusals: mixed kind -----------------------------------------------------------
    # All three come out of a "04_Rare" pool, so they share rarity 3 and the only thing that
    # can make _grind refuse is the kind. That branch (grinder.py:897) has never run.
    mixed_kind = (
        give(RARE_WEAPONS, 40, 1)
        + give(G.POOLS[("shield", 3)], 40, 1)
        + give(G.POOLS[("grenade", 3)], 40, 1)
    )
    check(
        "the mixed-kind feed is three different kinds at one rarity",
        len({G._kind(i) for i in mixed_kind}) == 3 and len({G._rarity(i) for i in mixed_kind}) == 1,
        f"kinds {[G._kind(i) for i in mixed_kind]}, rarities {[G._rarity(i) for i in mixed_kind]}",
    )
    n, m = len(bag()), money(P)
    G._grind(P, mixed_kind)
    check(
        "a gun, a shield and a grenade together are refused and nothing is taken",
        len(bag()) == n and money(P) == m,
        f"backpack {len(bag()) - n}, money {money(P) - m}",
    )

    # --- refusals: no money, on both paths ----------------------------------------------
    for ground in (False, True):
        G.loot_on_ground.value = ground
        where_it_goes = "onto the ground" if ground else "into the backpack"
        broke_feed = three_rare_weapons()
        held = money(P)
        add_money(-held)
        n, before_p = len(bag()), pickups()
        G._grind(P, broke_feed)
        check(
            f"a player who cannot pay is refused and loses no items, grinding {where_it_goes}",
            len(bag()) == n and len(broke_feed) == 3,
            f"backpack moved by {len(bag()) - n}, with {len(broke_feed)} items fed in "
            f"(3 means the refusal was about the money and nothing else)",
        )
        if ground:
            check(
                "a player who cannot pay gets no loot on the floor",
                pickups() == before_p,
                f"{len(pickups() - before_p)} new pickups appeared",
            )
        add_money(held)

    # --- the ground path ----------------------------------------------------------------
    G.loot_on_ground.value = True
    gfeed = three_rare_weapons()
    if len(gfeed) == 3:
        want_rarity = G._rarity(gfeed[0])
        n, before_p = len(bag()), pickups()
        G._grind(P, gfeed)
        new_pickups = [p for p in unrealsdk.find_all("WillowPickup") if str(p) not in before_p]
        check(
            "grinding onto the ground consumes every item fed in",
            len(bag()) - n == -3,
            f"backpack moved by {len(bag()) - n}",
        )
        check(
            "grinding onto the ground puts exactly one new pickup in the world",
            len(new_pickups) == 1,
            f"{len(new_pickups)} new pickups",
        )
        # The audit reads the pickup's item off `.Inventory`; that is a guess and it is not
        # marked as measured anywhere, so every plausible field is tried and named.
        holder, tried = None, []
        for field in ("Inventory", "InventoryItem", "PickupableInventory", "InvItem"):
            tried.append(field)
            if not new_pickups:
                break
            try:
                value = getattr(new_pickups[0], field)
            except Exception:  # noqa: BLE001
                continue
            if value is not None:
                holder = value
                break
        check(
            "the pickup the grinder drops holds an item of the rarity that went in",
            holder is not None and G._rarity(holder) == want_rarity,
            f"tried {tried}; found {holder!r}"
            + (f" rarity {G._rarity(holder)} against {want_rarity}" if holder is not None else ""),
        )

    # --- the charge failing after the loot already exists --------------------------------
    # grinder.py:948-949 returns after _drop_loot has already spawned the pickup.
    G.loot_on_ground.value = True
    G._charge = lambda controller, amount: False
    ffeed = three_rare_weapons()
    n, before_p = len(bag()), pickups()
    G._grind(P, ffeed)
    check(
        "a grind whose charge fails leaves no loot on the floor",
        pickups() == before_p,
        f"{len(pickups() - before_p)} pickups appeared for a grind that was never paid for",
    )
    check(
        "a grind whose charge fails keeps the items it was fed",
        len(bag()) == n,
        f"backpack moved by {len(bag()) - n}",
    )
    G._charge = REAL_CHARGE

    # --- the shared loot-burst template --------------------------------------------------
    check(
        "dropping loot does not permanently change the game's own loot-burst template",
        [str(x) for x in CDO.ItemPools] == [str(x) for x in CDO_POOLS]
        and CDO.CircularScatterRadius == CDO_RADIUS,
        f"pools now {[str(x) for x in CDO.ItemPools]}, radius now {CDO.CircularScatterRadius} "
        f"(was {[str(x) for x in CDO_POOLS]} / {CDO_RADIUS})",
    )

    # --- which duplicates get spent -------------------------------------------------------
    # grinder.py:487 says "Newest first, so grinding spends the duplicates rather than a
    # favourite", and grinder.py:489 then takes found[:wanted]. That is only true if the
    # backpack array lists the newest item first.
    src = give(RARE_WEAPONS, 40, 1)[0]
    before = {str(i) for i in bag()}
    P.GetPawnInventoryManager().ClientAddWeaponToBackpack(src.DefinitionData, 0, False, 0, 0)
    copy = added(before)
    order = [str(i) for i in bag()]
    check(
        "the backpack appends your newest copy at the END, which is the order the grinder now "
        "takes from",
        bool(copy) and order and order[-1] == str(copy[0]),
        f"the new copy landed at index {order.index(str(copy[0])) if copy else '?'} of {len(order)}",
    )

except Exception:  # noqa: BLE001
    # regress.py has no try/except anywhere, so one raise costs the whole scoreboard and the
    # bridge answers with a traceback instead of results. Not repeating that here.
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    G._note = REAL_NOTE
    G._charge = REAL_CHARGE
    G.how_many.value = SAVED_HOW
    G.cost_per_level.value = SAVED_COST
    G.loot_on_ground.value = SAVED_GROUND
    try:
        CDO.ItemPools = CDO_POOLS
        CDO.CircularScatterRadius = CDO_RADIUS
    except Exception as ex:  # noqa: BLE001
        print(f"could not put the loot-burst template back: {ex!r}")
    manager = P.GetPawnInventoryManager()
    left = [i for i in G._backpack(P) if str(i) not in KEEP]
    for item in left:
        try:
            manager.RemoveInventoryFromBackpack(item)
        except Exception as ex:  # noqa: BLE001
            print(f"could not remove {item}: {ex!r}")
    add_money(SAVED_MONEY - money(P))
    print(f"\ncleaned up {len(left)} spawned items, money back to ${money(P):,} "
          f"(started at ${SAVED_MONEY:,})")
    print("loot dropped on the floor by the ground-path checks is left where it fell.")
    if NOTES:
        print("the grinder said: " + " | ".join(NOTES))

summary()
