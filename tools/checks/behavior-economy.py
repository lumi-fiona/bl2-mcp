# Cheaper prices (economy.py) - behavior checks
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-economy.py
#
# Every object this file writes is a shop/tuning DEFINITION, never the player's own wallet,
# inventory or save data - the same category of thing revive.py's and difficulty.py's own
# checks already write and restore live. Each write is followed, in the same block, by the
# read that proves it landed, and the finally puts every value back to what was found first,
# whether or not everything above it succeeded.
reset()

import unrealsdk
from bl2_modern import core
from bl2_modern.features import economy as E

was = {
    "cheaper_sdus": E.cheaper_sdus.value,
    "vendor_prices": E.vendor_prices.value,
}
real_get_pc = E.get_pc
real_find = E._find
snap_vanilla = dict(E._vanilla)
snap_vanilla_attrs = dict(E._vanilla_attrs)
snap_sdu_prices = list(E._vanilla_sdu_prices) if E._vanilla_sdu_prices is not None else None
snap_vendor_touched = E._vendor_prices_touched

# Every name the finally block restores, given a safe default here rather than only where each
# is first found below - an exception early in the try (before a given section runs at all)
# must still leave the finally block something defined to test, not a NameError that replaces
# whatever was actually being reported.
sdu_obj = slots_obj = health_obj = torgue_obj = respec_obj = None
sdu_before = slots_before = health_before = torgue_before = respec_before = None
found: list = []
sample_before = None
torgue_attr = respec_mid = respec_leaf = None
# The attribute beside the skill-respec constant is an object reference, and None is a real
# value it can hold - so "never read" needs its own marker rather than None.
UNREAD = object()
respec_attr_before = UNREAD


class FakeClient:
    WorldInfo = type("W", (), {"NetMode": 3})()

    def GetCurrentPlaythrough(self):
        return 2


def _read(cls, path, attr):
    try:
        obj = unrealsdk.find_object(cls, path)
        return obj, float(getattr(obj, attr))
    except Exception as ex:
        return None, f"unreadable: {ex!r}"


def _read_formula(cls, path, mid, leaf):
    try:
        obj = unrealsdk.find_object(cls, path)
        node = getattr(obj.ValueFormula, mid)
        return obj, float(getattr(node, leaf))
    except Exception as ex:
        return None, f"unreadable: {ex!r}"


try:
    # --- is the feature wired in at all -----------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Cheaper prices"), None)
    check(
        "the Cheaper prices feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "both switches ship OFF, because both are economy changes",
        E.cheaper_sdus.default_value is False and E.vendor_prices.default_value is False,
        f"cheaper_sdus default={E.cheaper_sdus.default_value!r}, "
        f"vendor_prices default={E.vendor_prices.default_value!r}",
    )
    check(
        "the core will re-apply this at the main menu, after the bundled patch has run",
        feature is not None and feature.writes_game_data and feature.apply is E._apply_all,
        f"writes_game_data={getattr(feature, 'writes_game_data', None)}, "
        f"apply={getattr(feature, 'apply', None)}",
    )
    check(
        "the per-map and per-restock hooks are both carried to the core",
        feature is not None
        and any(h is E.on_character_live for h in feature.hooks)
        and any(h is E.on_vending_generate for h in feature.hooks),
        getattr(feature, "hooks", None),
    )
    check(
        "changing either switch writes it straight away",
        E.cheaper_sdus.on_change_anytime is E._on_change
        and E.vendor_prices.on_change_anytime is E._on_change,
        (E.cheaper_sdus.on_change_anytime, E.vendor_prices.on_change_anytime),
    )

    # --- the off-and-never-touched guard, before anything else sets _vendor_prices_touched --
    if not E._vendor_prices_touched:
        real_ammo_scan = E._ammo_type_resolvers
        scanned = []
        E._ammo_type_resolvers = lambda: (scanned.append(1) or real_ammo_scan())
        E.vendor_prices.value = False
        E._apply_vendor_prices(playthrough=None)
        E._ammo_type_resolvers = real_ammo_scan
        check(
            "switched off and never touched, applying does not even scan for price objects",
            not scanned,
            f"the full-class scan ran {len(scanned)} time(s) with the switch off and untouched",
        )
    else:
        print("[SKIP] the off-and-never-touched guard - this session had already touched "
              "vendor prices before this file ran, so the untouched case cannot be observed")

    # --- a DLC object that is simply not on this map is quiet, not a line per restock --------
    # Five of the paths this feature writes only exist on DLC maps, and both hooks run on every
    # map load and every vending machine restock. A miss must be remembered so it is only ever
    # reported once, and must never raise.
    MISSING = "NoSuchPackage.NoSuchObject"
    E._missing_logged.discard(MISSING)
    first_miss = E._find("PopulationFactoryVendingMachine", MISSING)
    logged_once = MISSING in E._missing_logged
    second_miss = E._find("PopulationFactoryVendingMachine", MISSING)
    check(
        "an object that is not loaded returns nothing, does not raise, and is only ever "
        "reported once no matter how many restocks ask for it",
        first_miss is None and second_miss is None and logged_once,
        f"first={first_miss!r}, second={second_miss!r}, remembered={logged_once}",
    )

    # --- Cheaper bonus backpack upgrades: the SDU price list --------------------------------
    sdu_obj, sdu_before = None, None
    try:
        sdu_obj = unrealsdk.find_object("BalanceModifierDefinition", E.SDU_BALANCE_MOD)
        sdu_before = [float(e.EridiumCostForUpgrade) for e in sdu_obj.AdditionalBackpackSDUUpgrades]
    except Exception as ex:
        sdu_obj = None
        print(f"[SKIP] {E.SDU_BALANCE_MOD} is not loaded here ({ex!r}) - the SDU price list "
              f"checks need it loaded, which may need a real UVHM character")

    slots_obj, slots_before = _read(
        "ConstantAttributeValueResolver", E.SLOTS_PER_UPGRADE, "ConstantValue",
    )
    if slots_obj is None:
        print(f"[SKIP] {E.SLOTS_PER_UPGRADE} is not loaded here ({slots_before})")

    if sdu_obj is not None:
        check(
            "the bonus backpack SDU prices read as four numbers before anything is touched",
            len(sdu_before) == 4,
            f"AdditionalBackpackSDUUpgrades = {sdu_before}",
        )

        E.cheaper_sdus.value = True
        E._apply_cheaper_sdus()
        now = [float(e.EridiumCostForUpgrade) for e in sdu_obj.AdditionalBackpackSDUUpgrades]
        check(
            "turning the switch on writes the four cheaper prices onto the object the shop reads",
            [round(v, 3) for v in now] == [round(v, 3) for v in E.WANTED_SDU_PRICES],
            f"AdditionalBackpackSDUUpgrades = {now}, wanted {list(E.WANTED_SDU_PRICES)}",
        )
        if slots_obj is not None:
            check(
                "and the backpack-slots-per-upgrade constant is set to 3 at the same time",
                abs(float(slots_obj.ConstantValue) - E.SLOTS_PER_UPGRADE_WANTED) < 1e-6,
                f"ConstantValue = {slots_obj.ConstantValue}",
            )

        E.cheaper_sdus.value = False
        E._apply_cheaper_sdus()
        restored = [float(e.EridiumCostForUpgrade) for e in sdu_obj.AdditionalBackpackSDUUpgrades]
        check(
            "turning the switch back off restores the prices this file found on arrival, not "
            "the game's textbook 50/100/150/200 - whatever was really there",
            [round(v, 3) for v in restored] == [round(v, 3) for v in sdu_before],
            f"AdditionalBackpackSDUUpgrades = {restored}, arrival was {sdu_before}",
        )
        if slots_obj is not None:
            check(
                "and the slots-per-upgrade constant is restored too",
                abs(float(slots_obj.ConstantValue) - slots_before) < 1e-6,
                f"ConstantValue = {slots_obj.ConstantValue}, arrival was {slots_before}",
            )

    # --- Cheaper ammo, health, respecs and DLC vendors: representative objects --------------
    health_obj, health_before = _read(
        "ConstantAttributeValueResolver", E._SIMPLE_SCALED[2][0], "ConstantValue",
    )
    if health_obj is None:
        print(f"[SKIP] the health-vial price resolver is not loaded here ({health_before})")
    else:
        E.vendor_prices.value = True
        E._apply_vendor_prices(playthrough=2)  # UVHM
        wanted_uvhm = E._SIMPLE_SCALED[2][3] - 2 * E._SIMPLE_SCALED[2][4]
        check(
            "in UVHM, turning the switch on scales the health-vial price down to the UVHM number",
            abs(float(health_obj.ConstantValue) - wanted_uvhm) < 1e-6,
            f"ConstantValue = {health_obj.ConstantValue}, wanted {wanted_uvhm} for playthrough 2",
        )

        E._apply_vendor_prices(playthrough=0)  # NVHM, same session, no restart
        wanted_nvhm = E._SIMPLE_SCALED[2][3] - 0 * E._SIMPLE_SCALED[2][4]
        check(
            "moving to an earlier playthrough re-scales the same object without needing a restart",
            abs(float(health_obj.ConstantValue) - wanted_nvhm) < 1e-6,
            f"ConstantValue = {health_obj.ConstantValue}, wanted {wanted_nvhm} for playthrough 0",
        )

        E.vendor_prices.value = False
        E._apply_vendor_prices(playthrough=0)
        check(
            "turning the switch off restores the health-vial price this file found on arrival",
            abs(float(health_obj.ConstantValue) - health_before) < 1e-6,
            f"ConstantValue = {health_obj.ConstantValue}, arrival was {health_before}",
        )

    # --- the discovered "5 ammo types", the riskiest guess in this file ---------------------
    found = E._ammo_type_resolvers()
    print(f"economy: ammo-type discovery found {len(found)}: {[p for p, _ in found]}")
    # The ammo price objects only exist where ammo vendors do - measured 2026-08-20: on a
    # vendor-less map the live game holds 21 GD_Economy.BaseCost resolvers (guns, shields,
    # mods, health) and ZERO Ammo_* ones, and BL2Fix's own source guards every ammo lookup
    # with an if-it-exists for exactly this reason (its lines 1518-1560). So an empty find on
    # a map with no machines is the install working, not the discovery broken.
    _machines = [o for o in unrealsdk.find_all("WillowVendingMachine") if not o.Name.startswith("Default__")]
    if not found and not _machines:
        print(
            "[SKIP] the ammo-type discovery finds at least one price object to scale - no "
            "vending machines on this map, so the ammo price objects are not loaded at all; "
            "run this again in Sanctuary to count the real five",
        )
    else:
        check(
            "the ammo-type discovery finds at least one price object to scale, rather than silently "
            "scaling nothing",
            len(found) > 0,
            f"found {len(found)} with {len(_machines)} machines present - the spec expects 5 "
            f"(AR/SMG/pistol/shotgun/sniper); a different number is not necessarily a bug, but "
            f"needs a human to look at the printed path list above",
        )
    if found:
        sample_path, sample_obj = found[0]
        sample_before = float(sample_obj.ConstantValue)
        E.vendor_prices.value = True
        E._apply_vendor_prices(playthrough=2)
        wanted = E._AMMO_TYPE_BASE - 2 * E._AMMO_TYPE_STEP
        check(
            f"a discovered ammo-type resolver ({sample_path}) really gets scaled",
            abs(float(sample_obj.ConstantValue) - wanted) < 1e-6,
            f"ConstantValue = {sample_obj.ConstantValue}, wanted {wanted}",
        )
        E.vendor_prices.value = False
        E._apply_vendor_prices(playthrough=2)
        check(
            "and restored on the way back off",
            abs(float(sample_obj.ConstantValue) - sample_before) < 1e-6,
            f"ConstantValue = {sample_obj.ConstantValue}, arrival was {sample_before}",
        )

    # --- one flat item (Torgue featured cost) and one nested formula (skill respec) --------
    torgue_path, torgue_cls, torgue_attr, torgue_wanted = E._FLAT[0]
    torgue_obj, torgue_before = _read(torgue_cls, torgue_path, torgue_attr)
    if torgue_obj is None:
        print(f"[SKIP] the Torgue Token vendor is not loaded here ({torgue_before}) - it may "
              f"need the Torgue DLC content actually streamed in")
    else:
        E.vendor_prices.value = True
        E._scaled_write(torgue_path, torgue_cls, torgue_attr, torgue_wanted, True)
        check(
            "the Torgue Token vendor's featured-item cost is cut to the BL2Fix number",
            abs(float(getattr(torgue_obj, torgue_attr)) - torgue_wanted) < 1e-6,
            f"{torgue_attr} = {getattr(torgue_obj, torgue_attr)}, wanted {torgue_wanted}",
        )
        E._scaled_write(torgue_path, torgue_cls, torgue_attr, torgue_wanted, False)
        check(
            "and restored to whatever this file found there on arrival",
            abs(float(getattr(torgue_obj, torgue_attr)) - torgue_before) < 1e-6,
            f"{torgue_attr} = {getattr(torgue_obj, torgue_attr)}, arrival was {torgue_before}",
        )

    respec_path, respec_cls, respec_mid, respec_leaf, respec_wanted, respec_clears = E._FORMULA[0]
    check(
        "the skill-respec entry is the one marked as also clearing the attribute beside the "
        "number - BL2Fix writes both (init.py:1569-1570) and the number alone does nothing while "
        "that attribute is set",
        respec_clears is True,
        f"_FORMULA[0] = {E._FORMULA[0]!r}",
    )
    respec_obj, respec_before = _read_formula(respec_cls, respec_path, respec_mid, respec_leaf)
    if respec_obj is None:
        print(f"[SKIP] the skill-respec cost object is not loaded here ({respec_before})")
    else:
        respec_attr_before = getattr(
            getattr(respec_obj.ValueFormula, respec_mid), E.ATTRIBUTE_LEAF,
        )
        print(
            f"economy: ValueFormula.{respec_mid}.{E.ATTRIBUTE_LEAF} on arrival = "
            f"{respec_attr_before!r}",
        )
        E._formula_write(
            respec_path, respec_cls, respec_mid, respec_leaf, respec_wanted, True, respec_clears,
        )
        node = getattr(respec_obj.ValueFormula, respec_mid)
        check(
            "the skill-respec cost's nested formula field is written, not silently ignored",
            abs(float(getattr(node, respec_leaf)) - respec_wanted) < 1e-6,
            f"ValueFormula.{respec_mid}.{respec_leaf} = {getattr(node, respec_leaf)}, "
            f"wanted {respec_wanted}",
        )
        check(
            "and the attribute beside it is cleared in the same write, so the number is the one "
            "the game actually reads",
            getattr(node, E.ATTRIBUTE_LEAF) is None,
            f"ValueFormula.{respec_mid}.{E.ATTRIBUTE_LEAF} = "
            f"{getattr(node, E.ATTRIBUTE_LEAF)!r}",
        )
        E._formula_write(
            respec_path, respec_cls, respec_mid, respec_leaf, respec_wanted, False, respec_clears,
        )
        node = getattr(respec_obj.ValueFormula, respec_mid)
        check(
            "and restored to what this file found there on arrival",
            abs(float(getattr(node, respec_leaf)) - respec_before) < 1e-6,
            f"ValueFormula.{respec_mid}.{respec_leaf} = {getattr(node, respec_leaf)}, "
            f"arrival was {respec_before}",
        )
        # What "restored" means is the pack's own first-seen snapshot, which may predate this
        # file if the switch was already on when it started - so ask the pack, and fall back to
        # what this file read on arrival when the pack had never touched it before now.
        expected_attr = E._vanilla_attrs.get(
            f"{respec_path}.{respec_mid}.{E.ATTRIBUTE_LEAF}", respec_attr_before,
        )
        check(
            "including the attribute, which is put back to whatever was really there rather than "
            "left as None",
            getattr(node, E.ATTRIBUTE_LEAF) == expected_attr,
            f"ValueFormula.{respec_mid}.{E.ATTRIBUTE_LEAF} = "
            f"{getattr(node, E.ATTRIBUTE_LEAF)!r}, expected {expected_attr!r} "
            f"(this file found {respec_attr_before!r} on arrival)",
        )

    # --- co-op: a machine that joined someone else's game must not write on either hook -----
    if health_obj is not None:
        E.vendor_prices.value = True
        setattr(health_obj, "ConstantValue", health_before)  # known state before the guard test
        E.on_character_live(FakeClient(), None, None, None)
        check(
            "the per-map hook does not write anything for a machine that joined someone else's "
            "game - the host owns vendor prices",
            abs(float(health_obj.ConstantValue) - health_before) < 1e-6,
            f"ConstantValue = {health_obj.ConstantValue} after the spawn hook ran as a client, "
            f"arrival was {health_before}",
        )

        E.get_pc = lambda *_a, **_k: FakeClient()
        E.on_vending_generate(None, None, None, None)
        E.get_pc = real_get_pc
        check(
            "neither does the vending-machine-restock hook, for the same reason",
            abs(float(health_obj.ConstantValue) - health_before) < 1e-6,
            f"ConstantValue = {health_obj.ConstantValue} after the restock hook ran as a client, "
            f"arrival was {health_before}",
        )
        E.vendor_prices.value = False
        E._apply_vendor_prices(playthrough=0)

    # --- nothing here may ever raise into the game -------------------------------------------
    def _angry_find(cls, path):
        raise RuntimeError(f"simulated: {cls} lookup refused")

    E._find = _angry_find
    escaped = []
    for label, call in (
        ("cheaper SDUs", lambda: E._apply_cheaper_sdus()),
        ("vendor prices", lambda: E._apply_vendor_prices(2)),
        ("main-menu apply", lambda: E._apply_all()),
    ):
        try:
            call()
        except Exception as ex:
            escaped.append((label, ex))
    E._find = real_find
    check(
        "a lookup that refuses cannot throw out of any of the three entry points into the game",
        not escaped,
        f"{escaped!r}",
    )

finally:
    E._find = real_find
    E.get_pc = real_get_pc
    E._missing_logged.discard("NoSuchPackage.NoSuchObject")

    # Put every live game object back to what this file found on arrival, each independently
    # guarded so one failing restore cannot skip the ones after it.
    if sdu_obj is not None and sdu_before is not None:
        try:
            body = ",".join(f"(EridiumCostForUpgrade={p:g})" for p in sdu_before)
            pc().ConsoleCommand(f"set {E.SDU_BALANCE_MOD} AdditionalBackpackSDUUpgrades ({body})")
        except Exception as ex:
            print(f"could not restore the SDU price list: {ex!r}")
    if slots_obj is not None and isinstance(slots_before, float):
        try:
            slots_obj.ConstantValue = slots_before
        except Exception as ex:
            print(f"could not restore slots-per-upgrade: {ex!r}")
    if health_obj is not None and isinstance(health_before, float):
        try:
            health_obj.ConstantValue = health_before
        except Exception as ex:
            print(f"could not restore the health-vial price: {ex!r}")
    if found:
        try:
            found[0][1].ConstantValue = sample_before
        except Exception as ex:
            print(f"could not restore the sample ammo-type price: {ex!r}")
    if torgue_obj is not None and isinstance(torgue_before, float):
        try:
            setattr(torgue_obj, torgue_attr, torgue_before)
        except Exception as ex:
            print(f"could not restore the Torgue featured-item cost: {ex!r}")
    if respec_obj is not None and isinstance(respec_before, float):
        try:
            formula = respec_obj.ValueFormula
            node = getattr(formula, respec_mid)
            setattr(node, respec_leaf, respec_before)
            if respec_attr_before is not UNREAD:
                setattr(node, E.ATTRIBUTE_LEAF, respec_attr_before)
            setattr(formula, respec_mid, node)
            respec_obj.ValueFormula = formula
        except Exception as ex:
            print(f"could not restore the skill-respec cost: {ex!r}")

    E.cheaper_sdus.value = was["cheaper_sdus"]
    E.vendor_prices.value = was["vendor_prices"]
    E._vanilla.clear()
    E._vanilla.update(snap_vanilla)
    E._vanilla_attrs.clear()
    E._vanilla_attrs.update(snap_vanilla_attrs)
    E._vanilla_sdu_prices = snap_sdu_prices
    E._vendor_prices_touched = snap_vendor_touched

    check(
        "every switch and every object this file touched is back where it was found",
        E.cheaper_sdus.value == was["cheaper_sdus"]
        and E.vendor_prices.value == was["vendor_prices"]
        and E._find is real_find
        and E.get_pc is real_get_pc,
        f"cheaper_sdus={E.cheaper_sdus.value}, vendor_prices={E.vendor_prices.value}",
    )

summary()
