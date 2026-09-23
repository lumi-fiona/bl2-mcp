# The Golden Chest grinder (tickets 19 and 45) - the claims that hold inside one frame.
# Run: bash bl2-mcp/tools/run-checks.sh grinder     (a character must be loaded, in Sanctuary for
# the chest's own claims)
#
# The chest's own open, its loot moment 1.35 s later and the lid closing need time to pass, so they
# are not here: tickets 19 and 45 have them, measured with screenshots. Everything below uses items
# this file spawns, and puts back what it changes (money, eridium, the level-less list, the
# backpack count, the switch). A result laid in the closed chest and taken out again leaves it as
# it was: its detach event belongs to its Opened sequence (measured, ticket 45).
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
LAUNCHER = "GD_Weap_Launchers.A_Weapons.RL_Maliwan_2_Uncommon"
SMG = "GD_Weap_SMG.A_Weapons.SMG_Maliwan_2_Uncommon"
SHOTGUN = "GD_Weap_Shotgun.A_Weapons.SG_Torgue_2_Uncommon"
SNIPER = "GD_Weap_SniperRifles.A_Weapons.Sniper_Maliwan_2_Uncommon"

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
        G._remove(fresh)


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
    check("a used-up gun is set to leave the game (Destroy() from Python leaves it, measured)",
          0 < float(d.LifeSpan) < 1, f"LifeSpan {float(d.LifeSpan)}")

    # --- a result left on the floor goes in even with a full backpack ---------------------------
    e, = roll(JAKOBS)
    uid_e = G._uid(e)
    thrown = G._weapon_maker().CreateWeaponFromDef(copy.copy(e.DefinitionData), p.Pawn, False)
    manager.RemoveInventoryFromBackpack(e)
    G._remove(e)
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
    G._remove(f_)
    manager.UpdateBackpackInventoryCount()
    thrown.ItemLocation = 2
    pickup = thrown.DropFrom(unrealsdk.make_struct("Vector", X=loc.X, Y=loc.Y, Z=loc.Z), unrealsdk.make_struct("Vector"),
                             False, False, unrealsdk.make_struct("Vector"))
    G._outputs.append((unrealsdk.unreal.WeakPointer(pickup), uid_f))
    G.on_travel(None, None, None, None)  # what TravelToStation reaches before the map goes
    check("a result still lying there goes into the backpack when you travel",
          G._is_carried(p, uid_f) and not any(u == uid_f for _p, u in G._outputs),
          f"carried {G._is_carried(p, uid_f)}")

    # --- ticket 45: one gun lies where the chest's own first one of its kind does -------------
    kinds = {}
    for kind, balance in (("pistol", MAL2), ("launcher", LAUNCHER), ("smg", SMG), ("shotgun", SHOTGUN),
                          ("sniper", SNIPER)):
        kinds[kind], = roll(balance)
    sockets = {k: G._socket(g) for k, g in kinds.items()}
    check("a pistol lies at Pistol2, a launcher at Launcher1, every other gun at Gun1",
          sockets == {"pistol": "Pistol2", "launcher": "Launcher1", "smg": "Gun1", "shotgun": "Gun1",
                      "sniper": "Gun1"}, f"{sockets}")

    # --- Lumi, ticket 45: a perfected gun keeps its old name ---------------------------------
    # Into the backpack a gun's name is picked afresh from its parts; the Vladof barrel names a
    # Maliwan pistol "Umbrage". The control, with no kept name, shows the pick happening.
    vladof = unrealsdk.find_object("WeaponPartDefinition", "GD_Weap_Pistol.Barrel.Pistol_Barrel_Vladof")
    plain_title = unrealsdk.find_object("WeaponNamePartDefinition", "GD_Weap_Pistol.Name.Title_Maliwan.Title__Pistol")
    base_gun, = roll(MAL2)
    titles = {}
    for keep in (False, True):
        nd = copy.copy(base_gun.DefinitionData)
        nd.BarrelPartDefinition, nd.TitlePartDefinition = vladof, plain_title
        nd.UniqueId = G._new_uid(p)
        made_uids.append(int(nd.UniqueId))
        if keep:
            G._names[int(nd.UniqueId)] = G._name_parts(nd)
        new_gun = G._weapon_maker().CreateWeaponFromDef(nd, p.Pawn, False)
        manager.AddBackpackInventory(new_gun)
        in_bag = G._held(p, int(nd.UniqueId))
        titles[keep] = str(in_bag.DefinitionData.TitlePartDefinition.Name) if in_bag else None
        if in_bag != new_gun:
            G._remove(new_gun)
        G._names.pop(int(nd.UniqueId), None)
    check("into the backpack, the game names a gun by its parts (control: Vladof barrel -> Umbrage title)",
          titles[False] == "Title_Barrel_Vladof_Rapid", f"{titles}")
    check("a perfected gun keeps its old name into the backpack", titles[True] == "Title__Pistol", f"{titles}")

    chests = G._chests()
    check("the Golden Chest is in this map (the chest's claims below need Sanctuary)", len(chests) == 1,
          f"{len(chests)} chests")
    if chests:
        c = chests[0]
        use = int(G._price(c).UsabilityType)

        def chest_now():
            return (sorted(G._state(c)), int(c.bCostsToUse[use]), str(c.InteractionIconOverride[use]))

        # --- ticket 44: the prompt and the price ------------------------------------------------
        check("the chest's prompt is the game's own OPEN prompt reading GRINDER",
              G._icon is not None and c.InteractionIconOverride[use] == G._icon
              and str(G._icon.Text) == "GRINDER" and str(G._icon.Action) == "Use",
              f"{chest_now()}")
        check("the grinder's chest asks no golden key", int(c.bCostsToUse[use]) == 0, f"{chest_now()}")
        closed_price = G._price(c)
        closed_price.ApplyBehaviorToContext(c, unrealsdk.make_struct("BehaviorKernelInfo"), c, p.Pawn,
                                            None, unrealsdk.make_struct("BehaviorParameters"))
        check("the chest's own price step, as every close runs it, puts no price back",
              int(c.bCostsToUse[use]) == 0, f"{chest_now()}")
        was_ready = G._ready(c)
        G.enabled.value = False
        off = chest_now()
        G.enabled.value = True
        on = chest_now()
        check("switched off, the chest has its own prompt and its key price back (closed chest)",
              off[2] == "None" and (off[1] == 1 or not was_ready), f"{off}")
        check("switched on again, it is the grinder's chest again", on[1] == 0 and "SecondWindGrinder" in on[2],
              f"{on}")

        # --- ticket 45: the result lies in the chest as the chest's own loot does ---------------
        if G._ready(c) and not G._holding(c):
            before = chest_now()
            step = G._behaviour(c, "SpawningLoot", lambda b: b.Class.Name == "Behavior_AttachItems")
            green, = roll(JAKOBS)
            bag_before = sorted(G._uid(i) for i in G.carried(p))
            plain = G._weapon_maker().CreateWeaponFromDef(copy.copy(green.DefinitionData), p.Pawn, False)
            loose = plain.GetPickup(True, not step.bDisablePickups)
            check("a green gun's pickup would shrink away: the game gives it a lifespan",
                  loose is not None and float(loose.LifeSpan) > 0 and loose.IsTimerActive("ShrinkPickupBeforeDestruction"),
                  f"LifeSpan {getattr(loose, 'LifeSpan', None)}")
            G._discard(p, loose)
            check("a pickup that is not laid in goes away with its gun (nothing made for free)",
                  loose.bDeleteMe and loose.Inventory is None and 0 < float(plain.LifeSpan) < 1
                  and sorted(G._uid(i) for i in G.carried(p)) == bag_before,
                  f"pickup deleted {loose.bDeleteMe}, gun LifeSpan {float(plain.LifeSpan)}")
            data = copy.copy(green.DefinitionData)
            data.UniqueId = G._new_uid(p)
            laid = G._mount(p, c, data, int(unrealsdk.find_enum("PlayerMark").PM_Favorite), step)
            ok_ = laid is not None
            socket = G._socket(green)
            _s_ok, s_loc, s_rot = c.ObjectMesh.GetSocketWorldLocationAndRotation(
                socket, unrealsdk.make_struct("Vector"), unrealsdk.make_struct("Rotator"))
            check("the result is attached to the chest at its socket, on the bottom shelf",
                  ok_ and laid.bIsPickupAttachedToSomething and laid.Base == c and laid.bHardAttach
                  and str(laid.BaseBoneName) == "Bone_Bottom_Shelf",
                  f"base {getattr(laid, 'Base', None)}, bone {getattr(laid, 'BaseBoneName', None)}")
            check("it lies exactly on the socket, as the chest's own guns do",
                  ok_ and all(abs(a - b) < 0.2 for a, b in ((laid.Location.X, s_loc.X), (laid.Location.Y, s_loc.Y),
                                                           (laid.Location.Z, s_loc.Z)))
                  and (laid.Rotation.Pitch, laid.Rotation.Yaw, laid.Rotation.Roll) == (s_rot.Pitch, s_rot.Yaw, s_rot.Roll))
            check("it is not pickupable until the lid's animation says so, as the chest's own loot",
                  ok_ and not laid.bPickupable and int(laid.Inventory.ItemLocation) == 6)
            check("it is kept across level transitions exactly when the chest's loot is",
                  ok_ and bool(laid.bCanBeSavedAcrossLevelTransition) == (not c.WillLootableBeResetOnLevelLoad()))
            check("it lies there forever, as the chest's own purple loot does",
                  ok_ and float(laid.LifeSpan) == 0.0 and not laid.IsTimerActive("ShrinkPickupBeforeDestruction")
                  and int(laid.LifeSpanType) == int(unrealsdk.find_enum("EDropLifeSpanType").DROP_LiveForever))
            check("it carries the star, and its new id", ok_ and int(laid.Inventory.GetMark()) == int(
                unrealsdk.find_enum("PlayerMark").PM_Favorite) and G._uid(laid.Inventory) == int(data.UniqueId))
            check("the grinder sees the chest holding it (so it never closes the lid over it)",
                  ok_ and G._holding(c))
            if ok_:
                # Lumi: it stays in the chest until she takes it or leaves; a save carries it.
                outputs_before = list(G._outputs)
                G._outputs.append((unrealsdk.unreal.WeakPointer(laid), G._uid(laid.Inventory)))
                G.on_save(p, None, None, None)
                during = G._held(p, int(data.UniqueId)) is not None and G._holding(c)
                G.on_saved(p, None, None, None)
                after = G._held(p, int(data.UniqueId)) is None and G._holding(c) and not laid.bDeleteMe
                G._outputs[:] = outputs_before
                check("a save has the waiting result in the backpack it writes, and it stays in the chest",
                      during and after and manager.BackpackInventoryCount == len(backpack(p)),
                      f"during {during}, after {after}")
                G._discard(p, laid)
            check("taken out again, the closed chest is exactly as it was, and holds nothing",
                  chest_now() == before and not G._holding(c), f"{before} -> {chest_now()}")

finally:
    G.enabled.value = True
    restore()
    G._ids.clear()
    G._ids.update(ids_before)
    for uid in made_uids:
        item = G._held(p, uid)
        if item is not None:
            manager.RemoveInventoryFromBackpack(item)
            G._remove(item)
    manager.UpdateBackpackInventoryCount()
    pri.AddCurrencyOnHand(cur.CURRENCY_Credits, wallet_before[0] - pri.GetCurrencyOnHand(cur.CURRENCY_Credits))
    pri.AddCurrencyOnHand(cur.CURRENCY_Eridium, wallet_before[1] - pri.GetCurrencyOnHand(cur.CURRENCY_Eridium))

summary()
