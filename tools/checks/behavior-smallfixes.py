# Small fixes - checks for features/smallfixes.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-smallfixes.py
#
# All four mechanisms write real objects for real, if those objects happen to be loaded from
# wherever this runs - each one that is not found is an honest [SKIP], the same idiom
# one-key-refill.py uses for "no vending machines in this level". Like revive-dials.py, none of
# this claims to know the GAME'S shipped default: it proves self-consistent round-tripping -
# whatever was there the moment the feature first touched it is what "off" restores, which is
# exactly the contract the feature promises.
#
# The one thing here that is NOT round-tripping is the house rule that a switch nobody has
# touched writes nothing at all. That is checked directly: snapshots emptied, switch off, apply
# run, and then the snapshot must still be empty and the live objects untouched.
reset()

import unrealsdk

from bl2_modern import core
from bl2_modern.features import smallfixes as SF

was = {
    "ranger": SF.ranger_fix.value,
    "grog": SF.grog_reward.value,
    "vehicle": SF.vehicle_permaslag.value,
    "turret": SF.turret_speed.value,
}
# The feature's own first-seen memory, put back at the end so a later apply() in this same
# session reasons from what the pack found rather than from whatever this run left behind.
saved_memory = {
    "ranger": dict(SF._ranger_vanilla),
    "grog": dict(SF._grog_vanilla),
    "vehicle": dict(SF._vehicle_vanilla),
    "turret": dict(SF._turret_vanilla),
}

# What this file itself changed on real objects, so the finally block can put each one back.
touched: dict[str, object] = {}


def _find(cls, path):
    try:
        return unrealsdk.find_object(cls, path)
    except Exception:
        return None


try:
    # --- is the feature wired in at all ------------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Small fixes"), None)
    check(
        "the small-fixes feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "only the Ranger fix ships on; the other three change play, so they ship off",
        SF.ranger_fix.default_value is True
        and SF.vehicle_permaslag.default_value is False
        and SF.grog_reward.default_value is False
        and SF.turret_speed.default_value is False,
        f"ranger={SF.ranger_fix.default_value!r}, vehicle={SF.vehicle_permaslag.default_value!r}, "
        f"grog={SF.grog_reward.default_value!r}, turret={SF.turret_speed.default_value!r}",
    )
    check(
        "the core will re-apply all four at the main menu, and whenever settings are read",
        feature is not None and feature.writes_game_data and feature.apply is SF._apply_all,
        f"writes_game_data={getattr(feature, 'writes_game_data', None)}, "
        f"apply={getattr(feature, 'apply', None)}",
    )
    check(
        "both re-apply points are carried: every map arrival and getting in a vehicle",
        feature is not None
        and feature.on_arrival is SF.on_arrival
        and any(h is SF.on_driver_enter for h in feature.hooks),
        (getattr(feature, "on_arrival", None), getattr(feature, "hooks", None)),
    )
    check(
        "all four switches are carried to the mod menu, in order",
        feature is not None
        and list(feature.options)
        == [SF.ranger_fix, SF.grog_reward, SF.vehicle_permaslag, SF.turret_speed],
        [getattr(o, "identifier", o) for o in getattr(feature, "options", [])],
    )
    check(
        "every one of the four switches applies immediately instead of waiting for a relaunch",
        all(
            o.on_change_anytime is SF._on_change
            for o in (SF.ranger_fix, SF.grog_reward, SF.vehicle_permaslag, SF.turret_speed)
        ),
        [o.on_change_anytime for o in (SF.ranger_fix, SF.grog_reward, SF.vehicle_permaslag, SF.turret_speed)],
    )
    check(
        "no switch's menu text sends the reader off to a docstring or a source file",
        not any(
            word in o.description.lower()
            for o in (SF.ranger_fix, SF.grog_reward, SF.vehicle_permaslag, SF.turret_speed)
            for word in ("docstring", ".py", "needs_ingame_probes", "not yet implemented")
        ),
        [o.description for o in (SF.ranger_fix, SF.grog_reward, SF.vehicle_permaslag, SF.turret_speed)],
    )

    calls = []
    real_turret, real_vehicles = SF._apply_turret_speed, SF._apply_vehicles
    SF._apply_turret_speed = lambda: calls.append("turret")
    SF._apply_vehicles = lambda: calls.append("vehicles")
    try:
        SF.on_arrival(None)
        SF.on_driver_enter(None, None, None, None)
    finally:
        SF._apply_turret_speed, SF._apply_vehicles = real_turret, real_vehicles
    check(
        "an arrival re-applies the turret and the vehicle hook re-applies the vehicles",
        calls == ["turret", "vehicles"],
        f"calls={calls}",
    )

    # --- the house rule: a switch nobody has touched writes nothing --------------------------
    # Every switch is put off and every first-seen memory emptied, which is the state the pack is
    # in the moment it loads with everything off. Applying from there must not touch anything.
    for option in (SF.ranger_fix, SF.grog_reward, SF.vehicle_permaslag, SF.turret_speed):
        option.value = False
    SF._ranger_vanilla.clear()
    SF._grog_vanilla.clear()
    SF._vehicle_vanilla.clear()
    SF._turret_vanilla.clear()

    before_untouched = {}
    for cls, path in SF.TURRET_OBJECTS:
        obj = _find(cls, path)
        if obj is not None:
            before_untouched[path] = tuple(SF._num(getattr(obj, f)) for f in SF.TURRET_FIELDS)
    ranger_before = None
    ranger_obj = _find("ClassModDefinition", SF.RANGER_PATH)
    if ranger_obj is not None:
        try:
            ranger_before = bool(ranger_obj.AttributeSlotEffects[SF.RANGER_SLOT].bRunEffectsAsSkill)
        except Exception:
            ranger_before = None

    SF._apply_all()

    check(
        "with every switch off and nothing written yet, applying takes no snapshots at all",
        not SF._ranger_vanilla
        and not SF._grog_vanilla
        and not SF._vehicle_vanilla
        and not SF._turret_vanilla,
        f"ranger={SF._ranger_vanilla!r}, grog={SF._grog_vanilla!r}, "
        f"vehicle={list(SF._vehicle_vanilla)!r}, turret={SF._turret_vanilla!r}",
    )
    if before_untouched:
        after_untouched = {}
        for cls, path in SF.TURRET_OBJECTS:
            obj = _find(cls, path)
            if obj is not None:
                after_untouched[path] = tuple(SF._num(getattr(obj, f)) for f in SF.TURRET_FIELDS)
        check(
            "and it writes nothing either - the turret animation objects are exactly as found",
            after_untouched == before_untouched,
            f"{before_untouched!r} -> {after_untouched!r}",
        )
    else:
        print("[SKIP] Axton's turret animation objects are loaded here to prove nothing was written")
    if ranger_before is not None:
        try:
            now = bool(
                _find("ClassModDefinition", SF.RANGER_PATH)
                .AttributeSlotEffects[SF.RANGER_SLOT]
                .bRunEffectsAsSkill
            )
        except Exception:
            now = None
        check(
            "the Legendary Ranger is left alone too while nobody has touched its switch",
            now == ranger_before,
            f"{ranger_before!r} -> {now!r}",
        )

    # --- Legendary Ranger fix: the real object, or an honest skip ----------------------------
    ranger_obj = _find("ClassModDefinition", SF.RANGER_PATH)
    if ranger_obj is None:
        print(f"[SKIP] {SF.RANGER_PATH} is loaded here to test the Ranger fix for real")
    else:
        try:
            baseline = bool(ranger_obj.AttributeSlotEffects[SF.RANGER_SLOT].bRunEffectsAsSkill)
            touched["ranger"] = baseline
        except Exception as ex:
            print(f"[SKIP] the Ranger's attribute slot {SF.RANGER_SLOT} is readable here - {ex!r}")
        else:
            SF.ranger_fix.value = True
            SF._apply_ranger()
            on_value = bool(
                _find("ClassModDefinition", SF.RANGER_PATH)
                .AttributeSlotEffects[SF.RANGER_SLOT]
                .bRunEffectsAsSkill
            )
            check(
                "turning the Ranger fix on sets bRunEffectsAsSkill to True",
                on_value is True,
                f"reads {on_value!r}",
            )
            check(
                "and it remembered what it found before writing, so off has something to restore",
                SF._ranger_vanilla.get(SF.RANGER_PATH) == baseline,
                f"remembered {SF._ranger_vanilla.get(SF.RANGER_PATH)!r}, found {baseline!r}",
            )

            SF.ranger_fix.value = False
            SF._apply_ranger()
            off_value = bool(
                _find("ClassModDefinition", SF.RANGER_PATH)
                .AttributeSlotEffects[SF.RANGER_SLOT]
                .bRunEffectsAsSkill
            )
            check(
                "turning it back off restores whatever this check found there, not a guess",
                off_value == baseline,
                f"reads {off_value!r}, wanted the baseline {baseline!r}",
            )

    real_ranger_path = SF.RANGER_PATH
    SF.RANGER_PATH = "Nonexistent.NoSuchRangerClassMod"
    escaped = None
    try:
        SF.ranger_fix.value = True
        SF._apply_ranger()
    except Exception as ex:
        escaped = ex
    finally:
        SF.ranger_fix.value = False
        SF.RANGER_PATH = real_ranger_path
    check(
        "a missing Legendary Ranger object cannot throw out of apply and into the game",
        escaped is None,
        f"{escaped!r}",
    )

    # --- Grog Nozzle reward: the real objects, or an honest skip -----------------------------
    mission = _find("MissionDefinition", SF.GROG_MISSION_PATH)
    nozzle = _find("WeaponBalanceDefinition", SF.GROG_WEAPON_PATH)
    if mission is None or nozzle is None:
        print(
            f"[SKIP] the Grog Nozzle reward objects are loaded here to test for real - "
            f"mission found={mission is not None}, nozzle found={nozzle is not None}"
        )
    else:
        try:
            grog_baseline = list(mission.Reward.RewardItems)
            touched["grog"] = grog_baseline
        except Exception as ex:
            print(f"[SKIP] the mission's Reward.RewardItems is readable here - {ex!r}")
        else:
            SF.grog_reward.value = True
            SF._apply_grog()
            now = list(_find("MissionDefinition", SF.GROG_MISSION_PATH).Reward.RewardItems)
            check(
                "turning the Grog reward on replaces the mission's reward with just the Nozzle",
                len(now) == 1 and SF._path_of(now[0]) == SF._path_of(nozzle),
                f"RewardItems is now {[SF._path_of(x) for x in now]!r}",
            )

            SF.grog_reward.value = False
            SF._apply_grog()
            now2 = list(_find("MissionDefinition", SF.GROG_MISSION_PATH).Reward.RewardItems)
            check(
                "turning it back off restores whatever reward this check found there",
                [SF._path_of(x) for x in now2] == [SF._path_of(x) for x in grog_baseline],
                f"RewardItems is now {[SF._path_of(x) for x in now2]!r}, "
                f"wanted {[SF._path_of(x) for x in grog_baseline]!r}",
            )

    real_grog_path = SF.GROG_MISSION_PATH
    SF.GROG_MISSION_PATH = "Nonexistent.NoSuchMission"
    escaped = None
    try:
        SF.grog_reward.value = True
        SF._apply_grog()
    except Exception as ex:
        escaped = ex
    finally:
        SF.grog_reward.value = False
        SF.GROG_MISSION_PATH = real_grog_path
    check(
        "a missing Grog Nozzle mission cannot throw out of apply and into the game",
        escaped is None,
        f"{escaped!r}",
    )

    # --- Vehicle permaslag: whichever of the ten are actually loaded here --------------------
    found_vehicles = [(p, _find("VehicleClassDefinition", p)) for p in SF.VEHICLES]
    found_vehicles = [(p, o) for p, o in found_vehicles if o is not None]

    if not found_vehicles:
        print(
            "[SKIP] any of the ten named vehicles are loaded here to test vehicle permaslag for "
            "real - get into a runner and run this again; the resilience check below still runs"
        )
    else:
        vehicle_baseline = {}
        for path, v_obj in found_vehicles:
            try:
                vehicle_baseline[path] = SF._read_amp(v_obj)
            except Exception as ex:
                print(f"[SKIP] {path}'s amp numbers are readable here - {ex!r}")
        touched["vehicles"] = dict(vehicle_baseline)
        for path, values in vehicle_baseline.items():
            print(f"[INFO] {path} was found holding {SF._comparable(values)}")

        SF.vehicle_permaslag.value = True
        SF._apply_vehicles()
        for path in vehicle_baseline:
            try:
                live = SF._comparable(SF._read_amp(_find("VehicleClassDefinition", path)))
            except Exception as ex:
                print(f"[SKIP] {path}'s numbers could be compared after the write - {ex!r}")
                continue
            check(
                f"turning permaslag on zeroes every amp number on {path}",
                live == SF._comparable(SF.NEUTRAL),
                f"reads {live!r}, wanted {SF._comparable(SF.NEUTRAL)!r}",
            )

        SF.vehicle_permaslag.value = False
        SF._apply_vehicles()
        for path, baseline_values in vehicle_baseline.items():
            try:
                live = SF._comparable(SF._read_amp(_find("VehicleClassDefinition", path)))
            except Exception as ex:
                print(f"[SKIP] {path}'s numbers could be compared after restoring - {ex!r}")
                continue
            check(
                f"turning it back off restores {path}'s numbers to what this check found there",
                live == SF._comparable(baseline_values),
                f"reads {live!r}, wanted {SF._comparable(baseline_values)!r}",
            )

    real_vehicles_list = SF.VEHICLES
    SF.VEHICLES = ["Nonexistent.NoSuchVehicleClass"]
    escaped = None
    try:
        SF.vehicle_permaslag.value = True
        SF._apply_vehicles()
    except Exception as ex:
        escaped = ex
    finally:
        SF.vehicle_permaslag.value = False
        SF.VEHICLES = real_vehicles_list
    check(
        "a whole list of missing vehicles cannot throw out of apply and into the game",
        escaped is None,
        f"{escaped!r}",
    )

    # --- Turret throw speed: the real animation objects, or an honest skip -------------------
    turret_objs = [(cls, path, _find(cls, path)) for cls, path in SF.TURRET_OBJECTS]
    turret_objs = [(cls, path, o) for cls, path, o in turret_objs if o is not None]

    if not turret_objs:
        print(
            "[SKIP] Axton's two turret-throw animation objects are loaded here - load an Axton "
            "save and run this again for a real pass"
        )
    else:
        turret_baseline = {}
        for _cls, path, obj in turret_objs:
            try:
                turret_baseline[path] = tuple(float(getattr(obj, f)) for f in SF.TURRET_FIELDS)
            except Exception as ex:
                print(f"[SKIP] {path}'s animation numbers are readable here - {ex!r}")
        touched["turret"] = dict(turret_baseline)
        for path, values in turret_baseline.items():
            print(f"[INFO] {path} was found at {dict(zip(SF.TURRET_FIELDS, values))}")

        SF.turret_speed.value = True
        SF._apply_turret_speed()
        for _cls, path, obj in turret_objs:
            if path not in turret_baseline:
                continue
            live = tuple(SF._num(getattr(_find(_cls, path), f)) for f in SF.TURRET_FIELDS)
            check(
                f"turning the faster throw on plays {path} at full speed, blend times untouched",
                live == tuple(SF._num(v) for v in SF.TURRET_FAST),
                f"reads {dict(zip(SF.TURRET_FIELDS, live))}, wanted "
                f"{dict(zip(SF.TURRET_FIELDS, SF.TURRET_FAST))}",
            )

        SF.turret_speed.value = False
        SF._apply_turret_speed()
        for _cls, path, obj in turret_objs:
            if path not in turret_baseline:
                continue
            live = tuple(SF._num(getattr(_find(_cls, path), f)) for f in SF.TURRET_FIELDS)
            check(
                f"turning it back off restores {path} to what this check found there",
                live == tuple(SF._num(v) for v in turret_baseline[path]),
                f"reads {dict(zip(SF.TURRET_FIELDS, live))}, wanted "
                f"{dict(zip(SF.TURRET_FIELDS, turret_baseline[path]))}",
            )

    real_turret_objects = SF.TURRET_OBJECTS
    SF.TURRET_OBJECTS = (("WillowAnimDefinition", "Nonexistent.NoSuchThrowAnimation"),)
    escaped = None
    try:
        SF.turret_speed.value = True
        SF._apply_turret_speed()
    except Exception as ex:
        escaped = ex
    finally:
        SF.turret_speed.value = False
        SF.TURRET_OBJECTS = real_turret_objects
    check(
        "a missing turret animation object cannot throw out of apply and into the game",
        escaped is None,
        f"{escaped!r}",
    )

finally:
    # Real objects first, by hand, so a broken feature cannot leave the game changed.
    if "ranger" in touched:
        try:
            obj = unrealsdk.find_object("ClassModDefinition", SF.RANGER_PATH)
            obj.AttributeSlotEffects[SF.RANGER_SLOT].bRunEffectsAsSkill = touched["ranger"]
        except Exception:
            pass
    if "grog" in touched:
        try:
            unrealsdk.find_object("MissionDefinition", SF.GROG_MISSION_PATH).Reward.RewardItems = (
                touched["grog"]
            )
        except Exception:
            pass
    for path, values in dict(touched.get("vehicles", {})).items():
        try:
            SF._write_amp(unrealsdk.find_object("VehicleClassDefinition", path), values)
        except Exception:
            pass
    for path, values in dict(touched.get("turret", {})).items():
        try:
            obj = next(unrealsdk.find_object(c, p) for c, p in SF.TURRET_OBJECTS if p == path)
            for field, value in zip(SF.TURRET_FIELDS, values):
                setattr(obj, field, value)
        except Exception:
            pass

    # Then the feature's own memory and switches, so a later apply() reasons from what the pack
    # found rather than from whatever this run happened to cache.
    SF._ranger_vanilla.clear()
    SF._ranger_vanilla.update(saved_memory["ranger"])
    SF._grog_vanilla.clear()
    SF._grog_vanilla.update(saved_memory["grog"])
    SF._vehicle_vanilla.clear()
    SF._vehicle_vanilla.update(saved_memory["vehicle"])
    SF._turret_vanilla.clear()
    SF._turret_vanilla.update(saved_memory["turret"])

    SF.ranger_fix.value = was["ranger"]
    SF.grog_reward.value = was["grog"]
    SF.vehicle_permaslag.value = was["vehicle"]
    SF.turret_speed.value = was["turret"]

    check(
        "every switch and every first-seen memory is back where this file found it",
        SF.ranger_fix.value == was["ranger"]
        and SF.grog_reward.value == was["grog"]
        and SF.vehicle_permaslag.value == was["vehicle"]
        and SF.turret_speed.value == was["turret"]
        and dict(SF._turret_vanilla) == saved_memory["turret"]
        and dict(SF._ranger_vanilla) == saved_memory["ranger"],
        f"ranger={SF.ranger_fix.value!r}, grog={SF.grog_reward.value!r}, "
        f"vehicle={SF.vehicle_permaslag.value!r}, turret={SF.turret_speed.value!r}, "
        f"turret memory={SF._turret_vanilla!r}",
    )

summary()
