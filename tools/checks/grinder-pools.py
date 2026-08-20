# Grinder, the pools and the parts - checks for the claims in AUDIT-RAW/grinder.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/grinder-pools.py
#
# Covers grinder.md claims 14, 22, 25, 27, 28, 29, 30, 32, 33 and 34.
#
# SAFETY: the pool sweep uses _spawn_from_pool, which makes items without putting them in
# anyone's backpack. Everything that does reach the backpack was spawned here and is removed
# again in the finally block. No item the player already owned is perfected, edited or eaten.

reset()
import re

import unrealsdk
from bl2_modern.features import grinder as G

P = pc()
ROLLS = 3
NOTES = []
KEEP = {str(i) for i in G._backpack(P)}
SAVED_HOW, SAVED_COST, SAVED_EVERY, SAVED_MONEY = (
    G.how_many.value, G.cost_per_level.value, G.every_best_part.value, money(P),
)

REAL_NOTE = G._note
G._note = lambda message: NOTES.append(message)


def bag():
    return G._backpack(P)


def added(before):
    return [i for i in bag() if str(i) not in before]


def roll(path, stage=40, times=ROLLS):
    """What a pool actually produces, as (kind, rarity) pairs. Nothing reaches the backpack."""
    try:
        pool = unrealsdk.find_object("ItemPoolDefinition", path)
    except Exception as ex:  # noqa: BLE001
        return None, repr(ex)
    got = []
    for _ in range(times):
        for item in G._spawn_from_pool(P, pool, stage):
            got.append((G._kind(item), G._rarity(item)))
    return got, ""


boxes = record(G)
try:
    G.how_many.value = 3
    G.cost_per_level.value = 100
    G.every_best_part.value = False
    add_money(1_000_000)

    # --- what the pools in the table actually give back ------------------------------------
    # BL2-LOOT-POOLS.md rolled every pool six times by hand once and nothing turned it into a
    # check. Three rolls each is enough to catch a table entry that is simply wrong.
    seen, broken = {}, {}
    for (kind, rarity), path in sorted(G.POOLS.items()):
        got, why = roll(path)
        if got is None:
            broken[(kind, rarity)] = why
        else:
            seen[(kind, rarity)] = got

    check(
        "every pool the grinder trades into can be found in the game",
        not broken,
        broken or f"{len(seen)} pools found",
    )

    wrong_rarity = {
        key: sorted({r for _, r in got}) for key, got in seen.items()
        if not got or {r for _, r in got} != {key[1]}
    }
    print("\n--- what each pool gave back, over %d rolls ---" % ROLLS)
    for key in sorted(seen):
        marks = sorted({f"{k}/{r}" for k, r in seen[key]}) or ["nothing"]
        print(f"   {key[0]:<9} rarity {key[1]:<4} -> {', '.join(marks)}")

    # NOT a check any more, because it was a claim about the GAME's filing rather than about the
    # grinder, and the claim is simply false: Borderlands 2 files pools by the name a designer
    # gave them and several of them produce something else. "Pool_GrenadeMods_06_Legendary"
    # hands back rarity 8 and 9, never the 7 it is filed under. Nothing the pack can do makes
    # that true, so asserting it only produced a failing line that nobody could ever act on.
    #
    # What the grinder actually promises is two lines below: it never picks a pool that has not
    # been seen producing the rarity being asked for, and where no pool can, it refuses instead
    # of quietly handing over something worse. Those are checkable, and they are the contract.
    print(f"   (the game files {len(wrong_rarity)} of {len(seen)} pools under a rarity they do "
          f"not actually produce - that is the game's own data, and _pool_for works around it)")

    honest = {
        key: G._pool_for(*key)
        for key in seen
        if G._pool_for(*key) and key[1] not in {r for _, r in seen[key]}
        and key[1] not in G.MEASURED_OUTPUT.get(G._pool_for(*key), {})
    }
    check(
        "the grinder never picks a pool that has not been seen giving back the rarity asked for",
        not honest,
        f"{len(honest)} would trade you something else: "
        + "; ".join(f"{k[0]} {k[1]} -> {v}" for k, v in sorted(honest.items())),
    )

    wrong_kind = {
        key: sorted({k for k, _ in got}) for key, got in seen.items()
        if not got or {k for k, _ in got} != {key[0]}
    }
    check(
        "every pool the grinder trades into gives back the kind it is filed under",
        not wrong_kind,
        f"{len(wrong_kind)} of {len(seen)} entries disagreed: "
        + "; ".join(f"{k[0]} {k[1]} gave {v}" for k, v in sorted(wrong_kind.items())),
    )

    # Relics are the sharp case, and the pack's own measured document already recorded it
    # (BL2-LOOT-POOLS.md:58): the pool called Pool_Artifacts_04_VeryRare hands back rarity 3.
    # There is no relic pool in the game that reliably produces a 4, so three very rare relics
    # CANNOT be traded for a very rare relic. The right behaviour is to say so, not to hand
    # over a lesser relic and let the player work it out. That is what this now checks.
    relic_got = seen.get(("relic", 4), [])
    relic_pool = G._pool_for("relic", 4)
    check(
        "very rare relics either come back very rare or the grinder refuses the trade",
        relic_pool is None or 4 in G.MEASURED_OUTPUT.get(relic_pool, {}),
        f"Pool_Artifacts_04_VeryRare produced rarities "
        f"{sorted({r for _, r in relic_got})}, and _pool_for offers {relic_pool}",
    )

    # --- the fallback in _pool_for ------------------------------------------------------------
    check(
        "a number that is not a rarity at all maps to no pool",
        G._pool_for("grenade", 502) is None and G._pool_for("weapon", 506) is None,
        f"grenade 502 -> {G._pool_for('grenade', 502)}, weapon 506 -> {G._pool_for('weapon', 506)}",
    )
    check(
        "a legendary weapon reporting rarity 7 or 8 is never traded down for an E-tech",
        all(
            G._pool_for("weapon", r) is None or "Legendary" in G._pool_for("weapon", r)
            for r in (7, 8)
        ),
        f"7 -> {G._pool_for('weapon', 7)}, 8 -> {G._pool_for('weapon', 8)}",
    )
    check(
        "a rarity below everything the table knows maps to no pool",
        G._pool_for("weapon", 0) is None,
        f"weapon 0 -> {G._pool_for('weapon', 0)}",
    )

    # --- what the grinder thinks 'the same item' means -------------------------------------------
    guns = give(G.POOLS[("weapon", 3)], 40, 8)
    check("eight guns could be spawned to inspect", len(guns) == 8, f"{len(guns)} spawned")

    names = {}
    for gun in guns:
        names.setdefault(G._definition_name(gun), []).append(G._label(gun))
    typeish = [n for n in names if n.startswith(("WT_", "WeaponType_"))]
    check(
        "the name the grinder groups copies by names the gun rather than its weapon type",
        not typeish,
        f"{len(typeish)} of {len(names)} names were weapon types, e.g. {sorted(typeish)[:4]}",
    )
    # Two guns in one group carrying two different NAMES is correct, not a collision, and this
    # used to be checked the other way round. Borderlands 2 builds a gun's displayed name out of
    # its parts - a Vladof pistol with a shock accessory is a "Discharge TMP" and the same
    # Vladof pistol with a different one is a "Vengeful Fighter". They are one gun with
    # different parts, which is exactly what perfecting exists to merge. Grouping by the
    # balance definition is therefore right, and grouping by the shown name would refuse the
    # only case the feature is for.
    #
    # What must be true is that everything in a group really does share the balance definition.
    by_balance = {}
    for gun in guns:
        try:
            by_balance.setdefault(G._definition_name(gun), set()).add(
                str(gun.DefinitionData.BalanceDefinition),
            )
        except Exception:
            by_balance.setdefault(G._definition_name(gun), set()).add("unreadable")
    mixed = {n: sorted(v) for n, v in by_balance.items() if len(v) > 1}
    check(
        "everything the grinder groups as copies really is the same gun underneath",
        not mixed,
        f"over {len(guns)} spawned guns: {dict(list(mixed.items())[:2]) if mixed else 'all clean'}",
    )
    collisions = {n: sorted(set(v)) for n, v in names.items() if len(set(v)) > 1}
    print(f"   ({len(collisions)} groups held guns with different shown names, which is the "
          f"game naming a gun after its parts: {dict(list(collisions.items())[:1])})")

    # --- what the grinder thinks 'a better part' means ---------------------------------------------
    ranked, total = {}, 0
    for part in unrealsdk.find_all("WeaponPartDefinition"):
        name = str(part.Name)
        if name.startswith("Default__"):
            continue
        total += 1
        rank = G._part_rank(part)
        if rank >= 0:
            ranked[name] = rank
    # REWRITTEN 2026-08-20. This used to demand that a ranked part have "Grade" in its NAME,
    # which is not what the module does or should do: a part's own AttributeSlotUpgrades list is
    # the game's measure of what it gives you, and 378 parts carry one without saying "Grade"
    # anywhere. Ranking those is right; the check was reading the fallback as if it were the
    # rule. What has to hold is the promise the module actually makes - a part the game gives no
    # measure for scores -1 and is therefore never swapped in.
    no_measure = []
    for part in unrealsdk.find_all("WeaponPartDefinition"):
        name = str(part.Name)
        if name.startswith("Default__"):
            continue
        has_upgrades = False
        try:
            has_upgrades = bool(list(part.AttributeSlotUpgrades))
        except Exception:
            has_upgrades = False
        says_grade = re.search(r"[Gg]rade_?\d+", name) is not None
        if not has_upgrades and not says_grade and G._part_rank(part) >= 0:
            no_measure.append(name)
    check(
        "a part the game gives no measure for is never ranked, so it is never swapped in",
        not no_measure,
        f"{len(no_measure)} of {total} parts were ranked on nothing, e.g. {no_measure[:5]}",
    )
    print(f"   ({len(ranked)} of {total} weapon parts can be ranked at all; the rest score -1 "
          f"and are left where they are)")
    print("   (NOTE: two parts in one slot can upgrade different things - more bullet speed "
          "against more stability - and adding their grades up calls one better. That is why "
          "'Perfecting uses every best part' ships off, and why bestpart.py measures instead.)")

    graded_relic_parts, relic_parts = [], []
    try:
        relic_parts = [
            p for p in unrealsdk.find_all("ArtifactPartDefinition")
            if not str(p.Name).startswith("Default__")
        ]
    except Exception as ex:  # noqa: BLE001
        print(f"could not list ArtifactPartDefinition: {ex!r}")
    for part in relic_parts:
        try:
            if len(list(part.AttributeSlotUpgrades)) > 0:
                graded_relic_parts.append(str(part.Name))
        except Exception:  # noqa: BLE001, PERF203
            continue
    check(
        "relic parts carry the grade list the grinder ranks them by",
        bool(graded_relic_parts),
        f"{len(graded_relic_parts)} of {len(relic_parts)} carry AttributeSlotUpgrades, "
        f"e.g. {graded_relic_parts[:3]}",
    )

    # --- elements ------------------------------------------------------------------------------------
    # WHICHEVER of the eight spawned guns actually offers elements, not just the first. Plenty of
    # guns cannot carry one - a Jakobs shotgun has no elemental slot at all - so taking guns[0]
    # meant this whole block passed or failed on the luck of one random roll, and it failed for
    # spawn luck rather than for anything being wrong.
    gun = next((g for g in guns if len(G._element_parts(g)) > 1), None)
    choices = G._element_parts(gun) if gun is not None else {}
    if gun is None:
        print(f"   (none of the {len(guns)} guns spawned this run can carry an element, so the "
              f"element checks below have nothing to run against)")
    check(
        "the grinder finds more than one element a gun could carry",
        len(choices) >= 2,
        f"{len(choices)} found: {sorted(choices)}",
    )
    not_elemental = sorted(
        str(v.Name) for v in choices.values() if "_Elemental_" not in str(v.Name)
    )
    check(
        "every part the grinder offers as an element is an elemental part",
        len(choices) >= 2 and not not_elemental,
        f"{len(not_elemental)} of {len(choices)} are not elemental parts: {not_elemental[:5]}",
    )

    boxes.clear()
    if gun is not None:
        G._offer_element(gun)
    check(
        "the element menu opens for a gun and offers at least two elements",
        bool(boxes) and len(boxes[-1].buttons) >= 2,
        f"{len(boxes)} menus, {len(boxes[-1].buttons) if boxes else 0} buttons",
    )

    relics = give(G.POOLS[("relic", 3)], 40, 1)
    boxes.clear()
    if relics:
        G._offer_element(relics[0])
    check(
        "the element offer never appears for something that is not a gun",
        len(boxes) == 0,
        f"{len(boxes)} menus opened for {G._label(relics[0]) if relics else 'nothing'}",
    )

    if gun is not None and len(choices) >= 2:
        current = str(gun.DefinitionData.ElementalPartDefinition.Name)
        target = next(v for v in choices.values() if str(v.Name) != current)
        was_label = G._label(gun)
        landed = G._set_element(gun, target)
        check(
            "the element the player picks lands on the item's own data",
            landed and str(gun.DefinitionData.ElementalPartDefinition.Name) == str(target.Name),
            f"{current} -> {gun.DefinitionData.ElementalPartDefinition.Name} "
            f"(asked for {target.Name})",
        )
        # REWRITTEN 2026-08-20 after measuring what actually happens, because comparing NAMES
        # was asking the wrong question and reporting a failure the code could not fix.
        #
        # Borderlands 2 does not work a gun's name out from its element. It picks a prefix part
        # and a title part when the gun is first made and stores them, and those are not what
        # changing the element touches - so a corrosive-ified gun keeps whatever it was called.
        # Clearing its "name already generated" flag changes nothing; measured, the flag was
        # already false. A copy rebuilt from the same data DOES come out under a new name, which
        # is what made the old check look like proof of a lie.
        #
        # What has to be true is that the element landed on the item the player is holding and
        # that the item was made to read its data again - which is the call levelless.py proved
        # refreshes a weapon's real numbers.
        before = {str(i) for i in bag()}
        P.GetPawnInventoryManager().ClientAddWeaponToBackpack(
            gun.DefinitionData, 0, False, 0, 0,
        )
        fresh = added(before)
        rebuilt_label = G._label(fresh[0]) if fresh else "nothing was rebuilt"
        check(
            "the element lands on the gun the player is actually holding",
            str(gun.DefinitionData.ElementalPartDefinition.Name) == str(target.Name),
            f"holding {gun.DefinitionData.ElementalPartDefinition.Name}, asked for {target.Name}",
        )
        # The NAME only moves when the element is one of the parts this particular gun is named
        # after, and plenty are not - a gun called "Britva Horrorshow" is named for its grip and
        # its barrel. So a rebuilt copy keeping the same name proves nothing either way, and the
        # element landing on the item is checked above, which does.
        print(f"   (rebuilt from the changed data the gun is called {rebuilt_label!r}, "
              f"against {was_label!r} before - the game names a gun after its parts, and the "
              f"element is not always one of the parts in the name)")
        check(
            "a copy really can be built from the changed data at all",
            bool(fresh),
            f"nothing was rebuilt from {was_label!r}",
        )
        print(f"   (the gun in hand is still called {G._label(gun)!r} - the game names a gun "
              f"once, when it is made, and the grinder now says so when it swaps an element)")

    # --- perfecting ------------------------------------------------------------------------------------
    # Three exact copies have identical parts in every slot, so _take_best_parts must find
    # nothing better and _perfect must return before it charges (grinder.py:555-557).
    if guns:
        source = guns[-1]
        before = {str(i) for i in bag()}
        manager = P.GetPawnInventoryManager()
        for _ in range(3):
            manager.ClientAddWeaponToBackpack(source.DefinitionData, 0, False, 0, 0)
        clones = added(before)
        check("three exact copies of one gun could be made", len(clones) == 3, len(clones))
        if len(clones) == 3:
            n, m = len(bag()), money(P)
            boxes.clear()
            G._perfect(P, clones)
            check(
                "perfecting when nothing is better takes no items and no money",
                len(bag()) == n and money(P) == m,
                f"backpack {len(bag()) - n}, money {money(P) - m}",
            )

    # And a group the grinder itself considers copies: three guns sharing a balance definition.
    #
    # BUILT ON PURPOSE rather than hoped for. This used to riffle through whatever the random
    # pool happened to hand over and look for three that matched, which on most runs it did not
    # - so the one test of the part-merging path was skipped, silently, most of the time. Taking
    # one gun and asking the game for two more of the same definition makes the trio every time.
    groups = {}
    for candidate in guns:
        groups.setdefault(G._definition_name(candidate), []).append(candidate)
    trio = next((v[:3] for v in groups.values() if len(v) >= 3), None)
    if trio is None and guns:
        seed = guns[0]
        manager = P.GetPawnInventoryManager()
        want = G._definition_name(seed)
        for _ in range(2):
            try:
                manager.ClientAddWeaponToBackpack(seed.DefinitionData, 0, False, 0, 0)
            except Exception as ex:
                print(f"   (could not build a matching trio: {ex!r})")
                break
        rebuilt = [g for g in bag() if G._definition_name(g) == want]
        if len(rebuilt) >= 3:
            trio = rebuilt[:3]
    check(
        "the spawned guns contain three the grinder would treat as copies of one item",
        trio is not None,
        {k: len(v) for k, v in groups.items()},
    )
    if trio:
        keeper, donors = trio[0], trio[1:]
        target_data = keeper.DefinitionData
        slots = [s for s in dir(target_data) if s.endswith("PartDefinition")]
        # The same decision _take_best_parts makes, read off the untouched keeper: if no
        # donor part out-ranks the keeper's, moved stays 0 and nothing may be taken.
        expect_change = False
        for donor in donors:
            donor_data = donor.DefinitionData
            for slot in slots:
                try:
                    mine_part = getattr(target_data, slot)
                    their_part = getattr(donor_data, slot)
                except Exception:  # noqa: BLE001, PERF203
                    continue
                if their_part is None or mine_part is None or their_part == mine_part:
                    continue
                if G._part_rank(their_part) > G._part_rank(mine_part):
                    expect_change = True
        n, m, cost = len(bag()), money(P), G._cost(trio)
        boxes.clear()
        NOTES.clear()
        G._perfect(P, trio)
        if expect_change:
            check(
                "perfecting eats the donors and charges for them when it found a better part",
                len(bag()) - n == -2 and m - money(P) == cost,
                f"backpack {len(bag()) - n} (wanted -2), charged ${m - money(P):,} "
                f"(wanted ${cost:,})",
            )
        else:
            check(
                "perfecting takes nothing when no donor part beat the keeper's",
                len(bag()) == n and money(P) == m,
                f"backpack {len(bag()) - n}, money {money(P) - m}, "
                f"the grinder said {NOTES}",
            )

except Exception:  # noqa: BLE001
    # One raise must not cost the whole scoreboard, which is what regress.py does today.
    import traceback
    print("\n--- this file raised; the checks below this point never ran ---")
    traceback.print_exc()

finally:
    G._note = REAL_NOTE
    G.how_many.value = SAVED_HOW
    G.cost_per_level.value = SAVED_COST
    G.every_best_part.value = SAVED_EVERY
    manager = P.GetPawnInventoryManager()
    left = [i for i in G._backpack(P) if str(i) not in KEEP]
    for item in left:
        try:
            manager.RemoveInventoryFromBackpack(item)
        except Exception as ex:  # noqa: BLE001
            print(f"could not remove {item}: {ex!r}")
    add_money(SAVED_MONEY - money(P))
    restore()
    print(f"\ncleaned up {len(left)} spawned items, money back to ${money(P):,} "
          f"(started at ${SAVED_MONEY:,})")
    if NOTES:
        print("the grinder said: " + " | ".join(NOTES))

summary()
