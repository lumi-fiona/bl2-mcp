# The Golden Chest grinder (ticket 19) - the claims that hold inside one frame.
# Run: bash bl2-mcp/tools/run-checks.sh grinder     (a character must be loaded)
#
# The chest's own open, its loot moment 1.35 s later and the lid closing need time to pass, so they
# are not here: ticket 19's answer has them, measured with screenshots. Everything below uses items
# this file spawns, and puts back what it changes (money, eridium, the level-less list, the
# backpack count).
reset()

import copy
import types

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook

from bl2_modern import core
from bl2_modern.features import grinder as G

p = pc()
manager = p.GetPawnInventoryManager()
pri = p.PlayerReplicationInfo
cur = unrealsdk.find_enum("ECurrencyType")
lvl = level(p)
MAL2 = "GD_Weap_Pistol.A_Weapons.Pistol_Maliwan_2_Uncommon"      # four elements on its list
HELLFIRE = "GD_Weap_SMG.A_Weapons_Legendary.SMG_Maliwan_5_HellFire"  # fire only
JAKOBS = "GD_Weap_Pistol.A_Weapons.Pistol_Jakobs_2_Uncommon"      # element list switched off

made_uids = []
ids_before = set(G._ids)
wallet_before = (pri.GetCurrencyOnHand(cur.CURRENCY_Credits), pri.GetCurrencyOnHand(cur.CURRENCY_Eridium))


def roll(balance, n=1, stage=None):
    bal = unrealsdk.find_object("WeaponBalanceDefinition", balance)
    pool = unrealsdk.find_class("ItemPool").ClassDefaultObject
    out = []
    for _ in range(n):
        ok, items = pool.SpawnBalancedInventoryFromInventoryBalanceDefinition(bal, 1, stage or lvl, 0, p, [])
        manager.AddBackpackInventory(items[0])
        uid = G._uid(items[0])
        made_uids.append(uid)
        out.append(G._held(p, uid))
    return out


def attributes_vs_fresh(gun):
    fresh = G._weapon_maker().CreateWeaponFromDef(copy.copy(gun.DefinitionData), p.Pawn, False)
    try:
        names = G._attributes(gun.Class)
        return {n: (round(float(getattr(gun, n)), 4), round(float(getattr(fresh, n)), 4))
                for n in names if round(float(getattr(gun, n)), 4) != round(float(getattr(fresh, n)), 4)}
    finally:
        fresh.Destroy()


def state():
    return (pri.GetCurrencyOnHand(cur.CURRENCY_Credits), pri.GetCurrencyOnHand(cur.CURRENCY_Eridium),
            sorted(G._uid(i) for i in G.carried(p)), sorted(G._ids), G._job is not None)


try:
    # --- it is loaded, and it is one switch ------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Grinder"), None)
    check("the grinder feature loaded", feature is not None and feature.failed is None,
          getattr(feature, "failed", "missing"))
    check("its switch is 'Enable the grinder', and it is on",
          G.enabled.identifier == "Enable the grinder" and G.enabled.value is True)
    check("the level-less list is kept per character under its old name",
          G.PER_CHARACTER and G.marked.identifier == "Level-less items"
          and any(o is G.marked for o in core.all_save_options()))
    check("no key opens it any more (key H was dropped)",
          not any(k.identifier == "Open the grinder" for k in core.all_keybinds()))

    # --- read once per load, never per frame -------------------------------------------------
    check("the cached list matches what the character's save holds",
          G._ids == {int(x) for x in (G.marked.value or [])}, f"{sorted(G._ids)}")
    reads = {"n": 0}

    def _count(*_):
        reads["n"] += 1

    add_hook("WillowGame.WillowPlayerController:GetCachedSaveGame", Type.PRE, "grinder-check", _count)
    try:
        for _ in range(120):
            G.on_tick(p, None, None, None)
    finally:
        remove_hook("WillowGame.WillowPlayerController:GetCachedSaveGame", Type.PRE, "grinder-check")
    check("120 ticks of the grinder copy the save 0 times (the old code: once a tick)",
          reads["n"] == 0, f"{reads['n']} copies")

    # --- prices -------------------------------------------------------------------------------
    prices = {r: G.eridium_cost(types.SimpleNamespace(RarityLevel=r)) for r in (1, 2, 3, 4, 5, 6, 9, 10)}
    check("eridium by rarity: white 5, green 10, blue 20, purple 35, anything above 50",
          prices == {1: 5, 2: 10, 3: 20, 4: 35, 5: 50, 6: 50, 9: 50, 10: 50}, f"{prices}")

    # --- guns to test with ---------------------------------------------------------------------
    a, b = roll(MAL2, 2)
    fixed, = roll(HELLFIRE)
    jakobs, = roll(JAKOBS)
    shield = give("GD_Itempools.ShieldPools.Pool_Shields_All_01_Common", lvl, 1)[0]
    made_uids.append(G._uid(shield))
    check("the test guns and a shield were made", None not in (a, b, fixed, jakobs, shield))

    # --- which parts can move ------------------------------------------------------------------
    check("the element moves on a gun whose list has several (Maliwan pistol)",
          "ElementalPartDefinition" in G._slots(a))
    check("the element stays on a fixed-element gun (Hellfire) and a Jakobs",
          "ElementalPartDefinition" not in G._slots(fixed) and "ElementalPartDefinition" not in G._slots(jakobs))
    choices = G.part_choices(a, b)
    check("the part list is exactly the copy's parts that differ from yours",
          all(getattr(b.DefinitionData, s) == part and getattr(a.DefinitionData, s) != part for s, part in choices)
          and all(s in dict(choices) for s in G._slots(a)
                  if getattr(b.DefinitionData, s) is not None and getattr(b.DefinitionData, s) != getattr(a.DefinitionData, s)),
          f"{[(s, G.part_label(x)) for s, x in choices]}")

    # --- refusals take nothing ------------------------------------------------------------------
    chest_like = None  # a refusal never reaches the chest
    before = state()
    pri.AddCurrencyOnHand(cur.CURRENCY_Eridium, -pri.GetCurrencyOnHand(cur.CURRENCY_Eridium))
    check("not enough eridium is refused", "eridium" in (G.levelless_refusal(p, a) or ""), G.levelless_refusal(p, a))
    G._start_levelless(p, chest_like, G._uid(a))
    pri.AddCurrencyOnHand(cur.CURRENCY_Eridium, 500)
    check("a shield is refused as not a gun", G.levelless_refusal(p, shield) == "Only guns can be made level-less.")
    G._start_levelless(p, chest_like, G._uid(shield))
    G._ids.add(G._uid(a))  # a is level-less for the rest of this file (put back at the end)
    check("an already level-less gun is refused", G.levelless_refusal(p, a) == "That gun is already level-less.")
    G._start_levelless(p, chest_like, G._uid(a))
    held = next((e for e in equipped(p) if G._is_gun(e)), None)
    if held is not None:
        check("a gun in your hands is refused", "hands" in (G.levelless_refusal(p, held) or ""), G.levelless_refusal(p, held))
    check("a different gun is refused as the copy",
          G.perfect_refusal(p, a, jakobs, "BarrelPartDefinition") == "The copy has to be another copy of the same gun.")
    G._start_perfect(p, chest_like, G._uid(a), G._uid(jakobs), "BarrelPartDefinition")
    check("a gun that is not level-less is refused as the target",
          "Only level-less guns" in (G.perfect_refusal(p, b, a, "BarrelPartDefinition") or ""))
    G._start_perfect(p, chest_like, G._uid(b), G._uid(a), "BarrelPartDefinition")
    b.SetMark(unrealsdk.find_enum("PlayerMark").PM_Favorite)
    check("a starred copy is not offered, and is refused", not any(G._uid(c) == G._uid(b) for c in G.copies_of(p, a))
          and "starred" in (G.perfect_refusal(p, a, b, choices[0][0] if choices else "BarrelPartDefinition") or ""))
    b.SetMark(unrealsdk.find_enum("PlayerMark").PM_Standard)
    if choices:
        pri.AddCurrencyOnHand(cur.CURRENCY_Credits, -pri.GetCurrencyOnHand(cur.CURRENCY_Credits))
        check("not enough money is refused", "costs $" in (G.perfect_refusal(p, a, b, choices[0][0]) or ""),
              G.perfect_refusal(p, a, b, choices[0][0]))
        G._start_perfect(p, chest_like, G._uid(a), G._uid(b), choices[0][0])
        pri.AddCurrencyOnHand(cur.CURRENCY_Credits, before[0])
    pri.AddCurrencyOnHand(cur.CURRENCY_Eridium, before[1] - pri.GetCurrencyOnHand(cur.CURRENCY_Eridium))
    after = state()
    check("every refusal left money, eridium, the guns and the chest as they were",
          after[:3] == before[:3] and after[4] is False, f"{before[:2]} -> {after[:2]}, job {after[4]}")

    # --- the menus --------------------------------------------------------------------------
    boxes = record(G)
    G._main_menu(p, chest_like)
    check("the chest's menu has exactly the two tools",
          len(boxes) == 1 and boxes[0].names() == ["Make a gun level-less", "Perfect a gun"],
          f"{boxes[-1].names() if boxes else []}")
    pick(boxes[0], "Make a gun level-less")
    names = [x.name for x in boxes[-1].buttons] if len(boxes) == 2 else []
    eligible = [g for g in backpack(p) if G._is_gun(g) and G._uid(g) not in G._ids]
    check("the level-less list is the backpack's guns that are not level-less - no shield",
          len(names) == len(eligible) and all(G._name(shield) not in n for n in names),
          f"{len(names)} rows for {len(eligible)} such guns")
    restore()

    # --- the relevel matches a fresh gun --------------------------------------------------------
    c, = roll(MAL2, 1, max(1, lvl - 2))
    G._relevel_one(c, max(1, lvl - 1))
    G._relevel_one(c, lvl)
    diff = attributes_vs_fresh(c)
    check("a gun relevelled twice in place matches a freshly made one in every attribute",
          diff == {}, f"{diff}")

    # --- the card: level tab off only for the level-less gun's own card -------------------------
    wt = a.DefinitionData.WeaponTypeDefinition
    G.on_card(None, types.SimpleNamespace(InventoryItem=a), None, None)
    off_for_a = wt.bUsesPlayerLevelRequirement is False
    G.on_card_done(None, None, None, None)
    G.on_card(None, types.SimpleNamespace(InventoryItem=b), None, None)
    on_for_b = wt.bUsesPlayerLevelRequirement is True
    G.on_card_done(None, None, None, None)
    check("the level tab is off while the level-less gun's card is drawn, and back after",
          off_for_a and wt.bUsesPlayerLevelRequirement is True)
    check("the same weapon type keeps its level tab on another gun's card", on_for_b)
    G._flag_off(wt)  # as if the ground-card rule left it off
    G.on_card(None, types.SimpleNamespace(InventoryItem=b), None, None)
    check("a flag the ground rule left off goes back on before another card is drawn",
          wt.bUsesPlayerLevelRequirement is True)
    G.on_card_done(None, None, None, None)

    # --- using up keeps the backpack's count right --------------------------------------------
    d, = roll(JAKOBS)
    G._use_up(p, d)
    check("using up a gun keeps the backpack's count equal to what is in it",
          manager.BackpackInventoryCount == len(backpack(p)),
          f"count {manager.BackpackInventoryCount}, backpack {len(backpack(p))}")

    # --- a result left on the floor goes in even with a full backpack ---------------------------
    e, = roll(JAKOBS)
    uid_e = G._uid(e)
    thrown = G._weapon_maker().CreateWeaponFromDef(copy.copy(e.DefinitionData), p.Pawn, False)
    manager.RemoveInventoryFromBackpack(e)
    e.Destroy()
    manager.UpdateBackpackInventoryCount()
    thrown.ItemLocation = 2
    loc = p.Pawn.Location
    pickup = thrown.DropFrom(unrealsdk.make_struct("Vector", X=loc.X, Y=loc.Y, Z=loc.Z), unrealsdk.make_struct("Vector"),
                             False, False, unrealsdk.make_struct("Vector"))
    manager.BackpackInventoryCount = 99  # full, as far as the game can tell
    ok = G._hand_over(p, pickup, uid_e) if pickup is not None else False
    manager.UpdateBackpackInventoryCount()
    check("a result on the floor goes into a full backpack, and leaves no copy behind",
          ok and G._is_carried(p, uid_e) and pickup.Inventory is None,
          f"handed over {ok}, carried {G._is_carried(p, uid_e)}")

    # --- ...and goes along when you travel (the game saves only after arriving) ----------------
    f_, = roll(JAKOBS)
    uid_f = G._uid(f_)
    thrown = G._weapon_maker().CreateWeaponFromDef(copy.copy(f_.DefinitionData), p.Pawn, False)
    manager.RemoveInventoryFromBackpack(f_)
    f_.Destroy()
    manager.UpdateBackpackInventoryCount()
    thrown.ItemLocation = 2
    pickup = thrown.DropFrom(unrealsdk.make_struct("Vector", X=loc.X, Y=loc.Y, Z=loc.Z), unrealsdk.make_struct("Vector"),
                             False, False, unrealsdk.make_struct("Vector"))
    G._outputs.append((unrealsdk.unreal.WeakPointer(pickup), uid_f, __import__("time").monotonic()))
    G.on_travel(None, None, None, None)  # what TravelToStation reaches before the map goes
    check("a result still on the floor goes into the backpack when you travel",
          G._is_carried(p, uid_f) and not any(u == uid_f for _p, u, _t in G._outputs),
          f"carried {G._is_carried(p, uid_f)}")

finally:
    restore()
    G._ids.clear()
    G._ids.update(ids_before)
    for uid in made_uids:
        item = G._held(p, uid)
        if item is not None:
            manager.RemoveInventoryFromBackpack(item)
            item.Destroy()
    manager.UpdateBackpackInventoryCount()
    pri.AddCurrencyOnHand(cur.CURRENCY_Credits, wallet_before[0] - pri.GetCurrencyOnHand(cur.CURRENCY_Credits))
    pri.AddCurrencyOnHand(cur.CURRENCY_Eridium, wallet_before[1] - pri.GetCurrencyOnHand(cur.CURRENCY_Eridium))

summary()
