# The museum - does the safety check actually refuse things, does it add nothing while checking,
# and are the game's loot pools left exactly as they were?
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/the-museum.py
#
# This file spawns museum pieces and takes them straight back out. Every item id it created is
# recorded and only those ids are removed, so a colliding id can never cost you real gear - the
# same rule the level-less check uses.
#
# The most important check here is the CONTROL: an ordinary gun out of an ordinary loot pool is put
# through the same validation the museum uses. If the control fails, the museum's verdicts mean
# nothing and every "passed" in this file is a passed-by-accident.
reset()

import unrealsdk
from bl2_modern.features import museum as M
from bl2_modern.features import grinder as G

p = pc()

enabled_before = M.enabled.value
level_before = M.at_level.value
verdicts_before = dict(M._verdicts)
busy_before = M._busy


def uid(item):
    try:
        return int(item.DefinitionData.UniqueId)
    except Exception:
        return None


pre_uids = set()
for _item in backpack():
    pre_uids.add(uid(_item))
mine = set()


def pool_sizes():
    """How many entries each museum pool holds, so a write to one would show up."""
    sizes = {}
    for _name, kind, path, _find in M.COLLECTION:
        if kind != "pool" or not path:
            continue
        try:
            pool = unrealsdk.find_object("ItemPoolDefinition", path)
            sizes[path] = len(list(pool.BalancedItems))
        except Exception:
            sizes[path] = None
    return sizes


pools_before = pool_sizes()

try:
    check(
        "there is a live character to make museum pieces for",
        p is not None,
        f"controller={p}",
    )

    from bl2_modern import core

    entry = [f for f in core.all_features() if f.name == "The museum"]
    check(
        "the museum feature loaded",
        len(entry) == 1 and entry[0].failed is None,
        f"found {len(entry)}; failure={entry[0].failed if entry else 'n/a'}",
    )
    check(
        "it ships switched off, because it is the riskiest thing in the pack",
        M.enabled.default_value is False,
        f"default is {M.enabled.default_value!r}",
    )
    check(
        "the switch says plainly that these items may not survive another machine",
        "not running this pack" in M.enabled.description,
        f"description reads: {M.enabled.description[:160]!r}",
    )
    check(
        "the museum knows this machine is not a guest in someone else's game",
        M._is_client() is False,
        f"_is_client()={M._is_client()}; on a client the menu must refuse rather than spawn",
    )

    # --- THE CONTROL --------------------------------------------------------------------
    # An ordinary rare gun, made by the game's own pool. If the museum's validation says no to
    # this, the validation is broken and nothing else in this file can be believed.
    control = give(G.POOLS[("weapon", 4)], level(p), 1)
    control_item = control[0] if control else None
    if control_item is not None:
        mine.add(uid(control_item))
    check(
        "an ordinary gun could be spawned to check the checker against",
        control_item is not None,
        f"spawned {len(control)} from {G.POOLS[('weapon', 4)]}",
    )
    if control_item is not None:
        control_name = M._readable_name(control_item)
        check(
            "the game names an ordinary gun, so the naming probe works",
            bool(control_name),
            f"the game calls it {control_name!r}",
        )
        passed, why = M._passes_the_game_check(p, control_item)
        check(
            "an ordinary gun passes the game's own item check - THE CONTROL",
            passed is True,
            f"{why}. If this fails, every museum verdict below is meaningless and the two "
            f"validate functions are not being reached at all",
        )

    # A thing that is not an item at all must be refused, so the checker can say no.
    refused, why_refused = M._passes_the_game_check(p, p)
    check(
        "the item check refuses something that is not an item",
        refused is False,
        f"handed it the player controller and it said {refused!r} ({why_refused})",
    )

    # --- what the collection can find in this game ---------------------------------------
    found = {}
    for e in M.COLLECTION:
        name, kind, path, find_name = e
        found[name] = M._find(kind, path, find_name) is not None
    check(
        "at least some of the collection is present in the game right now",
        sum(found.values()) > 0,
        f"{sum(found.values())} of {len(found)} pieces found. Missing: "
        f"{[n for n, ok in found.items() if not ok]}",
    )
    harpoon = found.get("The Sage harpoon gun")
    scorpio = found.get("Axton's turret gun, in your hands")
    check(
        "the two pieces named by full path in BL2-LEVERS.md are found by that path",
        bool(harpoon) and bool(scorpio),
        "harpoon={0}, scorpio={1}, routes={2}".format(harpoon, scorpio, dict(M._found_by)),
    )

    # --- the check itself -----------------------------------------------------------------
    n_before = len(backpack())
    results = M._check_all(p)
    check(
        "checking every piece adds nothing at all to your backpack",
        len(backpack()) == n_before,
        f"{n_before} items before, {len(backpack())} after checking {len(results)} pieces. Every "
        f"probe is made and destroyed and must never reach the backpack",
    )
    check(
        "every piece in the collection got a verdict",
        len(results) == len(M.COLLECTION),
        f"{len(results)} verdicts for {len(M.COLLECTION)} pieces",
    )
    passers = [n for n, (ok, _) in results.items() if ok]
    failers = [(n, why) for n, (ok, why) in results.items() if not ok]
    check(
        "the check refuses at least something, rather than waving everything through",
        len(failers) > 0,
        f"{len(passers)} passed and {len(failers)} were refused. A run where nothing at all is "
        f"refused is suspicious - several of these pieces are named without a path and cannot "
        f"be found in every map. Refused: {failers[:4]}",
    )
    check(
        "the check passes at least one piece, so the museum is not empty",
        len(passers) > 0,
        f"passed: {passers}",
    )
    print(f"\nverdicts:\n" + "\n".join(f"   {'PASS' if ok else 'skip'}  {n}  -  {why}"
                                      for n, (ok, why) in sorted(results.items())))

    # --- NOTHING WAS ADDED TO A LOOT POOL --------------------------------------------------
    pools_after = pool_sizes()
    changed = [k for k in pools_before if pools_before[k] != pools_after.get(k)]
    check(
        "the museum did not add anything to any loot pool",
        not changed,
        f"these pools changed size: {[(k, pools_before[k], pools_after.get(k)) for k in changed]}. "
        f"The feature's whole promise is that the game's loot tables are never touched",
    )

    # --- handing one over ------------------------------------------------------------------
    if passers:
        first = [e for e in M.COLLECTION if e[0] == passers[0]][0]
        n_before = len(backpack())
        before_uids = {uid(i) for i in backpack()}
        M._give(p, first)
        added = [i for i in backpack() if uid(i) not in before_uids]
        for i in added:
            mine.add(uid(i))
        check(
            f"asking for {passers[0]} puts exactly one item in your backpack",
            len(backpack()) == n_before + 1 and len(added) == 1,
            f"{n_before} -> {len(backpack())} items, {len(added)} of them new",
        )
        if added:
            check(
                "the piece you were handed is one the game can name",
                bool(M._readable_name(added[0])),
                f"the game calls it {M._readable_name(added[0])!r}",
            )
            check(
                "the piece you were handed passes the game's own item check",
                M._passes_the_game_check(p, added[0])[0] is True,
                f"{M._passes_the_game_check(p, added[0])[1]} - this is the check that decides "
                f"whether a save load deletes it",
            )
            check(
                "the piece comes out at your level",
                abs(int(added[0].DefinitionData.GameStage) - level(p)) <= 1,
                f"you are level {level(p)}, it is level {added[0].DefinitionData.GameStage}",
            )

    # --- the menu ---------------------------------------------------------------------------
    boxes = record(M)
    try:
        M.enabled.value = True
        M._busy = False
        M._open_menu(p)
        check(
            "the menu opens",
            len(boxes) == 1,
            f"{len(boxes)} dialogs opened",
        )
        if boxes:
            names = boxes[0].names()
            check(
                "only pieces that passed the check are offered",
                all(n in passers or n == "Check every piece again" for n in names),
                f"offered {names}; passers were {passers}",
            )
            check(
                "every piece that passed is offered",
                all(n in names for n in passers),
                f"missing from the menu: {[n for n in passers if n not in names]}",
            )
            check(
                "there is a way to run the check again without taking anything",
                "Check every piece again" in names,
                f"buttons: {names}",
            )
            check(
                "the menu warns that these items may not survive another machine",
                "not running this pack" in str(boxes[0].kw.get("message", "")),
                f"the message reads {boxes[0].kw.get('message')!r}",
            )
    finally:
        restore()

    # --- switched off, the key does nothing ---------------------------------------------------
    M.enabled.value = False
    boxes = record(M)
    try:
        M._busy = False
        M._open_museum.callback()  # @keybind returns a KeybindType; the press is its callback
        check(
            "with the museum switched off, its key opens nothing",
            len(boxes) == 0,
            f"{len(boxes)} dialogs opened with the feature off",
        )
    finally:
        restore()

finally:
    M.enabled.value = enabled_before
    M.at_level.value = level_before
    M._verdicts.clear()
    M._verdicts.update(verdicts_before)
    M._busy = busy_before
    restore()

    manager = p.GetPawnInventoryManager() if p is not None else None
    taken_back = 0
    if manager is not None:
        for item in list(backpack()):
            u = uid(item)
            if u is None or u not in mine or u in pre_uids:
                continue
            try:
                manager.RemoveInventoryFromBackpack(item)
                taken_back += 1
            except Exception as ex:
                print(f"could not take back a spawned item ({u}): {ex!r}")
    left = [i for i in backpack() if uid(i) in mine and uid(i) not in pre_uids]
    print(
        f"cleanup: took back {taken_back} spawned items, {len(left)} still in the backpack; "
        f"switch back to {M.enabled.value!r}"
    )

summary()
