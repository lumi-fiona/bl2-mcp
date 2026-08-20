# Level-less gear - checks for the implementation as it stands after the 2026-08-20 rewrite.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/level-less-gear.py
#
# The file this replaces was written against the previous implementation, which built a fresh
# copy of an item and threw the old one away. That approach is gone: nothing is created and
# nothing is removed any more, the item re-initialises itself where it stands. Most of the old
# file's checks therefore described lines that no longer exist, and kept failing for it.
#
# Everything below operates on items spawned by this file. It never touches real gear except to
# read it, and it puts back anything it changes.
reset()

from bl2_modern.features import levelless as L

p = pc()
lvl = level(p)
mgr = p.GetPawnInventoryManager()
made = []
restore_marks = list(L.marked.value or [])
restore_levels = {}

try:
    # --- where gear lives ---------------------------------------------------------------
    n_back, n_worn = len(backpack(p)), len(equipped(p))
    check("worn and held gear is not in the backpack list",
          n_worn > 0 and not any(w is b for w in equipped(p) for b in backpack(p)),
          f"{n_back} in the backpack, {n_worn} worn or held")
    check("the feature looks at both lists, not just the backpack",
          len(L.carried(p)) == n_back + n_worn,
          f"carried {len(L.carried(p))} = {n_back} + {n_worn}")

    # --- every kind of item re-levels, in place -----------------------------------------
    for pool, kind in (
        ("GD_Itempools.WeaponPools.Pool_Weapons_All_04_Rare", "gun"),
        ("GD_Itempools.ShieldPools.Pool_Shields_All_04_Rare", "shield"),
        ("GD_Itempools.GrenadeModPools.Pool_GrenadeMods_04_Rare", "grenade mod"),
        ("GD_Itempools.ArtifactPools.Pool_Artifacts_03_Rare", "relic"),
        ("GD_Itempools.ClassModPools.Pool_ClassMod_04_Rare", "class mod"),
    ):
        seeded = give(pool, max(1, lvl - 10), 1)
        if not seeded:
            check(f"a {kind} could be seeded to test with", False, f"nothing came out of {pool}")
            continue
        made += seeded
        item = seeded[0]
        was = int(item.DefinitionData.GameStage)
        count_before = len(L.carried(p))
        moved = L._relevel_one(item, lvl)
        check(f"a {kind} follows your level", moved and int(item.DefinitionData.GameStage) == lvl,
              f"{was} -> {item.DefinitionData.GameStage}, returned {moved}")
        check(f"re-levelling a {kind} creates no second copy",
              len(L.carried(p)) == count_before, f"{count_before} -> {len(L.carried(p))}")

    # --- the case the whole feature exists for -------------------------------------------
    guns = [i for i in equipped(p) if i.Class.Name == "WillowWeapon"]
    if guns:
        held = min(guns, key=lambda w: int(w.DefinitionData.GameStage))
        uid = int(held.DefinitionData.UniqueId)
        restore_levels[uid] = (held, int(held.DefinitionData.GameStage))
        was_dmg = float(held.InstantHitDamage)
        was_stage = int(held.DefinitionData.GameStage)
        n_before = len(L.carried(p))
        L.mark(held)
        check("marking the gun you are HOLDING brings it to your level",
              int(held.DefinitionData.GameStage) == lvl, f"{was_stage} -> {held.DefinitionData.GameStage}")
        check("it is still equipped afterwards", bool(held.bReadied), f"readied={held.bReadied}")
        check("nothing was duplicated", len(L.carried(p)) == n_before,
              f"{n_before} -> {len(L.carried(p))}")
        check("it is still the same gun", int(held.DefinitionData.UniqueId) == uid)
        if was_stage < lvl:
            check("and it really hits harder, not just reads a bigger number",
                  float(held.InstantHitDamage) > was_dmg,
                  f"{was_dmg:.1f} -> {held.InstantHitDamage:.1f}")
        check("a second pass finds nothing left to do", L.relevel_all(p) == 0)

    # --- refusing, rather than pretending ------------------------------------------------
    class NoId:
        DefinitionData = None
    before = len(L.marked.value or [])
    check("an item with no id is refused rather than remembered",
          L.mark(NoId()) is False and len(L.marked.value or []) == before,
          f"list length {before} -> {len(L.marked.value or [])}")
    check("levelling to zero does nothing", L._relevel_one(made[0], 0) is False if made else True)
    check("an item already at your level is left alone",
          L._relevel_one(made[0], lvl) is False if made else True)

    # --- where the list is kept ----------------------------------------------------------
    check("the marked list is stored on the character, not the machine",
          L.PER_CHARACTER and type(L.marked).__name__ == "HiddenSaveOption",
          f"{type(L.marked).__name__}, per character = {L.PER_CHARACTER}")
    check("the marked list is a list of plain numbers, so it can be written to a save",
          all(isinstance(x, int) for x in (L.marked.value or [])), f"{L.marked.value}")

finally:
    for uid, (item, stage) in restore_levels.items():
        try:
            L._forget(uid)
            L._relevel_one(item, stage)
        except Exception:
            pass
    for m in made:
        try:
            L._forget(int(m.DefinitionData.UniqueId))
        except Exception:
            pass
        try:
            mgr.RemoveInventoryFromBackpack(m)
        except Exception:
            pass
    L.marked.value = restore_marks
    print(f"cleanup: took back {len(made)} spawned items, marked list restored to {L.marked.value}")

summary()
