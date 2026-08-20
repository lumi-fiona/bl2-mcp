# Raid access and Digistruct Peak - checks for features/raidandpeak.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-raidandpeak.py
#
# Earlier raid access writes a real MissionDefinition's Dependencies[0] for real, for whichever
# raid bosses' DLC content happens to be loaded right now - each one that is not loaded is
# reported as a [SKIP], not a failure, exactly like one-key-refill.py does for "no vending
# machines in this level".
#
# THE DIRECTION QUESTION IS THE POINT OF THIS FILE. BL2Fix's table claims a "default" value for
# each raid mission's Dependencies[0], and the feature's own name claims the switch makes raids
# come EARLIER. Both claims rest on the same unchecked assumption. So for every boss whose DLC is
# loaded, this prints the value the mission really arrived holding beside the value BL2Fix's table
# claims, and says whether they agree. Three lines of evidence, printed whether or not anything
# can be written. What the printout cannot settle is whether the adjusted mission is genuinely
# earlier in the story than the arrival one - that still wants somebody standing in the DLC.
#
# The Digistruct Peak chest hook is tested with stand-in objects throughout, the same style as
# one-key-refill.py's fake vending machines: a fake CostAmount holder and a fake player
# controller whose WorldInfo.Game and GetMapName() are both controlled by hand. That proves the
# REAL shipped hook function makes the right decision in all four host/map combinations, without
# needing to stand on Digistruct Peak to do it. Whether a real Behavior_SetUsabilityCost instance
# also exists in this level to try it against for real is a bonus, gated behind its own [SKIP].
reset()

import unrealsdk

from bl2_modern import core
from bl2_modern.features import raidandpeak as RP

was_raid = RP.raid_access.value
was_chest = RP.digipeak_chests.value
real_get_pc = RP.get_pc

# Every raid mission's real Dependencies[0] as a path name, remembered before this file changes
# any of them - a name rather than the object, so a map change cannot make it stale.
original_dependency: dict[str, str] = {}

# The feature's own first-seen memory, put back at the end.
saved_vanilla = dict(RP._raid_vanilla)
saved_reported = set(RP._raid_reported)


class _FakeWorld:
    def __init__(self, game, mapname):
        self.Game = game
        self._mapname = mapname

    def GetMapName(self, *_args):
        return self._mapname


class _FakePC:
    def __init__(self, game, mapname):
        self.WorldInfo = _FakeWorld(game, mapname)


class _FakeCost:
    def __init__(self, starting=5):
        self.CostAmount = starting


try:
    # --- is the feature wired in at all ----------------------------------------------------
    feature = next(
        (f for f in core.all_features() if f.name == "Raid access and Digistruct Peak"), None
    )
    check(
        "the raid-access-and-peak feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "both switches ship off - both touch balance or economy, so the house default is off",
        RP.raid_access.default_value is False and RP.digipeak_chests.default_value is False,
        f"raid_access default={RP.raid_access.default_value!r}, "
        f"digipeak_chests default={RP.digipeak_chests.default_value!r}",
    )
    check(
        "the core will re-apply raid access at the main menu, and whenever settings are read",
        feature is not None and feature.writes_game_data and feature.apply is RP._apply_raid_access,
        f"writes_game_data={getattr(feature, 'writes_game_data', None)}, "
        f"apply={getattr(feature, 'apply', None)}",
    )
    check(
        "the Digistruct Peak chest hook is carried so the menu switch can reach it",
        feature is not None and any(h is RP.on_usability_cost for h in feature.hooks),
        getattr(feature, "hooks", None),
    )
    check(
        "both switches are carried to the mod menu",
        feature is not None and list(feature.options) == [RP.raid_access, RP.digipeak_chests],
        [getattr(o, "identifier", o) for o in getattr(feature, "options", [])],
    )
    check(
        "changing raid access writes the new setting straight away instead of waiting for a relaunch",
        RP.raid_access.on_change_anytime is RP._on_change,
        RP.raid_access.on_change_anytime,
    )

    # --- earlier raid access: the pure logic, no real object needed -------------------------
    check(
        "a raid mission that cannot be found is reported as not-changed rather than raising",
        RP._set_dependency("Nonexistent.NoSuchRaidMission", "Nonexistent.NoSuchTarget") is False,
        "no exception escaped a lookup of two objects that do not exist",
    )

    # --- the house rule: a switch nobody has touched writes nothing --------------------------
    # The switch is put off first (which restores anything the feature wrote earlier this
    # session), then its first-seen memory is emptied - that is the state the pack is in the
    # moment it loads with the switch off. Applying from there must not touch a single mission.
    RP.raid_access.value = False
    RP._raid_vanilla.clear()

    def _dependency(raid_path):
        try:
            return RP._path_of(
                unrealsdk.find_object("MissionDefinition", raid_path).Dependencies[0]
            )
        except Exception:
            return None

    arrival = {p: _dependency(p) for p, _d, _a in RP._RAIDS}
    arrival = {p: v for p, v in arrival.items() if v is not None}

    RP._apply_raid_access()
    check(
        "with the switch off and nothing written yet, applying takes no snapshot at all",
        not RP._raid_vanilla,
        f"first-seen memory is {RP._raid_vanilla!r}",
    )
    if arrival:
        check(
            "and it writes nothing - every raid mission still depends on what it arrived on",
            {p: _dependency(p) for p in arrival} == arrival,
            f"{arrival!r} -> {({p: _dependency(p) for p in arrival})!r}",
        )
    else:
        print("[SKIP] any raid boss's DLC content is loaded here to prove nothing was written")

    # --- the evidence: what the game holds against what BL2Fix's table claims ----------------
    for raid_path, default_mission, adjusted_mission in RP._RAIDS:
        arrived = arrival.get(raid_path)
        if arrived is None:
            print(
                f"[SKIP] {raid_path} is loaded here - its DLC is probably not installed, or not "
                f"loaded from this point in the game, so its arrival value cannot be read"
            )
            continue
        agrees = arrived.lower().endswith(default_mission.lower())
        print(
            f"[INFO] {raid_path}\n"
            f"       arrived depending on : {arrived}\n"
            f"       BL2Fix's table calls : {default_mission}  -> "
            f"{'AGREES' if agrees else 'DISAGREES - the table is wrong about this game'}\n"
            f"       switching on writes  : {adjusted_mission}"
        )

    # --- earlier raid access: the real thing, per boss, or an honest skip -------------------
    for raid_path, default_mission, adjusted_mission in RP._RAIDS:
        arrived = arrival.get(raid_path)
        if arrived is None:
            continue
        try:
            adjusted_obj = unrealsdk.find_object("MissionDefinition", adjusted_mission)
        except Exception as ex:
            adjusted_obj = None
            print(f"[SKIP] {raid_path}'s adjusted mission is loaded here - {ex!r}")
        if adjusted_obj is None:
            continue
        original_dependency[raid_path] = arrived

        RP.raid_access.value = True
        RP._apply_raid_access()
        now = _dependency(raid_path)
        check(
            f"turning on earlier raid access repoints {raid_path} at BL2Fix's adjusted mission",
            now == RP._path_of(adjusted_obj),
            f"Dependencies[0] is {now!r}, wanted {RP._path_of(adjusted_obj)!r} - whether that "
            f"direction is really EARLIER is the separate question the [INFO] lines above feed",
        )
        check(
            f"and it remembered {raid_path}'s arrival value before writing over it",
            RP._raid_vanilla.get(raid_path) == arrived,
            f"remembered {RP._raid_vanilla.get(raid_path)!r}, arrived on {arrived!r}",
        )

        RP.raid_access.value = False
        RP._apply_raid_access()
        now2 = _dependency(raid_path)
        check(
            f"turning it back off restores what {raid_path} arrived holding, not a table value",
            now2 == arrived,
            f"Dependencies[0] is {now2!r}, arrived on {arrived!r}, BL2Fix's table would have "
            f"written {default_mission!r}",
        )

    # --- Digistruct Peak chests: the real hook, stand-in world ------------------------------
    RP.digipeak_chests.value = True
    RP.get_pc = lambda: _FakePC(game=object(), mapname="TestingZone_P")
    obj = _FakeCost()
    RP.on_usability_cost(obj, None, None, None)
    check(
        "host, on Digistruct Peak's map, switch on: the lever's cost is zeroed",
        obj.CostAmount == 0,
        f"CostAmount ended up {obj.CostAmount!r}",
    )

    RP.get_pc = lambda: _FakePC(game=object(), mapname="SomeOtherMap_P")
    obj2 = _FakeCost()
    RP.on_usability_cost(obj2, None, None, None)
    check(
        "host, but the wrong map: the cost is left alone",
        obj2.CostAmount == 5,
        f"CostAmount ended up {obj2.CostAmount!r}, wanted the untouched starting value 5",
    )

    RP.get_pc = lambda: _FakePC(game=None, mapname="TestingZone_P")
    obj3 = _FakeCost()
    RP.on_usability_cost(obj3, None, None, None)
    check(
        "a guest's own machine, even on the right map: the cost is left alone",
        obj3.CostAmount == 5,
        f"CostAmount ended up {obj3.CostAmount!r} - only the host should ever zero this",
    )

    RP.digipeak_chests.value = False
    RP.get_pc = lambda: _FakePC(game=object(), mapname="TestingZone_P")
    obj4 = _FakeCost()
    RP.on_usability_cost(obj4, None, None, None)
    check(
        "switching the feature off leaves the cost alone even for the host on the right map",
        obj4.CostAmount == 5,
        f"CostAmount ended up {obj4.CostAmount!r}",
    )

    # --- nothing here may ever raise, even handed a nonsense object -------------------------
    escaped = None
    RP.digipeak_chests.value = True
    RP.get_pc = lambda: _FakePC(game=object(), mapname="testingzone_p")
    try:
        RP.on_usability_cost(object(), None, None, None)  # no CostAmount attribute at all
    except Exception as ex:
        escaped = ex
    check(
        "an object with no CostAmount at all cannot throw out of the hook and into the game",
        escaped is None,
        f"{escaped!r}",
    )

    escaped = None
    try:
        RP.get_pc = lambda: (_ for _ in ()).throw(RuntimeError("no session"))
        RP.on_usability_cost(_FakeCost(), None, None, None)
    except Exception as ex:
        escaped = ex
    check(
        "no player controller yet cannot throw out of the hook either",
        escaped is None,
        f"{escaped!r}",
    )

    # --- a real object, if one happens to be in this level right now (bonus, not required) --
    RP.get_pc = real_get_pc
    try:
        real_costs = [
            o for o in unrealsdk.find_all("Behavior_SetUsabilityCost") if not o.Name.startswith("Default__")
        ]
    except Exception as ex:
        real_costs = []
        print(f"[SKIP] find_all(\"Behavior_SetUsabilityCost\") could even be asked - {ex!r}")

    if not real_costs:
        print(
            "[SKIP] a live Behavior_SetUsabilityCost instance exists in this level to try the "
            "real hook against - none found here; stand near anything with an eridium cost, or "
            "travel to Digistruct Peak, for a real-object pass"
        )
    else:
        sample = real_costs[0]
        before = sample.CostAmount
        try:
            RP.digipeak_chests.value = True
            RP.get_pc = lambda: _FakePC(game=object(), mapname="testingzone_p")
            RP.on_usability_cost(sample, None, None, None)
            check(
                "the real hook zeroes a real object's CostAmount under faked host+map conditions",
                sample.CostAmount == 0,
                f"{before!r} -> {sample.CostAmount!r}",
            )
        finally:
            sample.CostAmount = before

finally:
    RP.get_pc = real_get_pc

    # The missions this file wrote, put back by hand first, so a broken feature cannot leave the
    # game changed. The arrival value was kept as a path name rather than as the object it found,
    # because an object reference held across a map change can go stale.
    for raid_path, original in original_dependency.items():
        try:
            unrealsdk.find_object("MissionDefinition", raid_path).Dependencies[0] = (
                unrealsdk.find_object("MissionDefinition", original)
            )
        except Exception:
            pass
    restored_ok = all(
        RP._path_of(unrealsdk.find_object("MissionDefinition", raid_path).Dependencies[0])
        == original
        for raid_path, original in original_dependency.items()
    )

    # Then the feature's own memory, then the switches - in that order, because putting a switch
    # back fires the feature's own apply, and it must reason from the memory the pack had.
    RP._raid_vanilla.clear()
    RP._raid_vanilla.update(saved_vanilla)
    RP._raid_reported.clear()
    RP._raid_reported.update(saved_reported)
    RP.raid_access.value = was_raid
    RP.digipeak_chests.value = was_chest

    check(
        "every raid mission this file touched is back exactly where it was found, and both "
        "switches and the feature's own memory are back where they were",
        restored_ok
        and RP.raid_access.value == was_raid
        and RP.digipeak_chests.value == was_chest
        and dict(RP._raid_vanilla) == saved_vanilla,
        f"restored_ok={restored_ok}, raid_access={RP.raid_access.value}, "
        f"digipeak_chests={RP.digipeak_chests.value}, memory={RP._raid_vanilla!r}",
    )

summary()
