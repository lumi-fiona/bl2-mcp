# Extras and level scaling - checks for the claims in AUDIT-RAW/extras.md and AUDIT-RAW/level-scaling.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extras-and-scaling.py
#
# Nothing here touches the backpack. The weapon-scaling checks use grinder._spawn_from_pool,
# which asks the game to MAKE an item and hands it back without adding it anywhere - so no real
# gear is read, moved or destroyed.
#
# Two checks below are written to FAIL today, on purpose, because the claim they carry is false:
#   - "toggling Hide undiscovered missions takes effect immediately" (extras.py:43)
#   - "re-applying at the same percent writes nothing" (levelscaling.py:48)
# Each has a companion check stating what is actually true, so a fix flips one and not the other.

reset()

import pathlib
import re

import unrealsdk

from bl2_modern import core
from bl2_modern.features import extras as E
from bl2_modern.features import grinder as G
from bl2_modern.features import levelscaling as LS
from bl2_modern.patchfile import commands_from, sections_in

# --- everything that gets put back, captured before anything is touched -------------------

SAVED_PERCENT = LS.percent.value
SAVED_CALLBACK = LS.percent.on_change_anytime
SAVED_HIDE = E.hide_missions.value
SAVED_SWITCHES = {name: option.value for name, option in E._switches.items()}

RESOLVER = None
SAVED_CONSTANT = None
try:
    RESOLVER = unrealsdk.find_object("ConstantAttributeValueResolver", LS.TARGET)
    SAVED_CONSTANT = float(RESOLVER.ConstantValue)
except Exception:
    RESOLVER = None

# --- reading the extras file the way the pack read it ------------------------------------
#
# wanted_sections() is asked now rather than assumed, because the pack asks it at the moment it
# runs the patch (core.py:264). If a switch has been unticked since launch, this scan and what
# actually ran will disagree, and the resolve check below is where that would show up.

TEXT = (pathlib.Path(core.__file__).parent / "data" / "extras.txt").read_text(
    encoding="utf-8", errors="replace",
)
WANTED = E.wanted_sections()
CMDS, HOT, IGNORED = commands_from(TEXT, WANTED)

EVERYWHERE = CMDS + [c for lvl, c in HOT if lvl in ("None", "")]
GATED = [(lvl.lower(), c) for lvl, c in HOT if lvl not in ("None", "")]


def _parts(command):
    """`set <object> <property> <value>` -> the three pieces, or Nones if it is not that shape."""
    bits = command.split(None, 3)
    if len(bits) != 4:
        return None, None, None
    return bits[1], bits[2], bits[3]


def _resolve(token):
    """`Class'Package.Object'` or a bare path -> the live object, or None if it is not loaded."""
    if "'" in token:
        cls, _, inner = token.partition("'")
        inner = inner.rstrip("'")
    else:
        cls, inner = "Object", token
    for attempt in (cls, "Object"):
        try:
            found = unrealsdk.find_object(attempt, inner)
        except Exception:
            continue
        if found is not None:
            return found
    return None


_CONST = r"\(BaseValueConstant=([-0-9.]+)"


def _already_applied(obj, prop, want):
    """
    Does the live object already read back what its command asked for?

    Returns (True/False/None, what was seen). None means no comparison is written for that
    property, so it gets counted and named rather than quietly passing. The five properties
    below are every property the extras file uses today: 24 Description, 3 PartName,
    3 BalanceByRegion, 1 CostToResetSkillPoints, 1 ValueFormula.
    """
    if prop in ("Description", "PartName"):
        got = str(getattr(obj, prop))
        return got.strip() == want.strip(), repr(got[:70])
    if prop == "BalanceByRegion":
        asked = [float(x) for x in re.findall("MaxDefaultGameStage=" + _CONST, want)]
        got = [float(e.MaxDefaultGameStage.BaseValueConstant) for e in obj.BalanceByRegion]
        same = len(got) == len(asked) and all(abs(a - b) < 1e-3 for a, b in zip(got, asked))
        return same, f"{len(got)} regions, top stages {got[:3]} against asked {asked[:3]}"
    if prop == "CostToResetSkillPoints":
        got = float(obj.CostToResetSkillPoints.BaseValueScaleConstant)
        return abs(got - 1e-6) < 1e-9, f"scale {got!r}"
    if prop == "ValueFormula":
        got = float(obj.ValueFormula.Multiplier.BaseValueConstant)
        return abs(got - 0.01) < 1e-6, f"multiplier {got!r}"
    return None, "no comparison written for this property"


# Split by where each command came from, not lumped into one MISSING list. The 29 in CMDS are
# global singletons/CDOs that should resolve no matter where the game is standing; the ones
# from level=None hotfixes are, as of "Faster animations" (2026-08-20), mostly per-DLC or
# per-machine-type content that is only loaded on some maps - see the second check below for
# why demanding they all resolve here was the wrong assertion.
UNPARSEABLE = []
COMMAND_MISSING = []
HOTFIX_MISSING = []
WRONG = []
UNKNOWN = []
LOOKED_AT = 0
_CMDS_COUNT = len(CMDS)

for _i, _command in enumerate(EVERYWHERE):
    _path, _prop, _want = _parts(_command)
    if _path is None:
        UNPARSEABLE.append(f"unparseable: {_command[:60]}")
        continue
    _target = _resolve(_path)
    if _target is None:
        (COMMAND_MISSING if _i < _CMDS_COUNT else HOTFIX_MISSING).append(_path[:70])
        continue
    LOOKED_AT += 1
    try:
        _verdict, _seen = _already_applied(_target, _prop, _want)
    except Exception as _ex:
        _verdict, _seen = False, f"reading {_prop} raised {_ex!r}"
    if _verdict is None:
        UNKNOWN.append(f"{_prop} on {_path[:50]}")
    elif not _verdict:
        WRONG.append(f"{_prop} on {_path[:50]} reads {_seen}")


try:
    # --- extras: the commands ------------------------------------------------------------

    # A skill belonging to a character you are not playing is NOT a missing object, and treating
    # it as one is what made this fail. MEASURED 2026-08-20 as Zer0: the three that would not
    # resolve were Gaige's Best Friends Forever tree and two of Krieg's Mania skills, which live
    # in GD_Tulip and GD_Lilac - packages the game only loads for the character who owns them.
    #
    # This is not a hole in the pack. The bundled patch runs when a character comes alive, so on
    # the machine where somebody IS playing Gaige, her package is loaded by then and the command
    # lands. Splitting them out here keeps the check able to fail for a genuinely wrong path
    # while not failing for a character nobody at this keyboard is playing.
    OTHER_CHARACTERS = ("GD_Tulip", "GD_Lilac", "GD_Aster", "GD_Anemone")
    elsewhere = [m for m in COMMAND_MISSING if any(pkg in m for pkg in OTHER_CHARACTERS)]
    really_missing = [m for m in COMMAND_MISSING if m not in elsewhere]
    check(
        "every extras command that runs on its own (not a level=None hotfix) names an "
        "object the game can find",
        not really_missing and not UNPARSEABLE and len(CMDS) > 0,
        f"{len(CMDS)} standalone commands, {IGNORED} lines ignored, "
        f"{len(really_missing)} unresolved: {really_missing[:4]}, "
        f"{len(UNPARSEABLE)} unparseable: {UNPARSEABLE[:2]}",
    )
    if elsewhere:
        print(f"   ({len(elsewhere)} name skills belonging to a character nobody here is "
              f"playing, so their package is not loaded: {[m[:46] for m in elsewhere]})")

    # DIAGNOSED 2026-08-20. This used to lump the level=None hotfixes in with the 29 commands
    # above and demand every one of them resolve too - true back when "everywhere" meant a
    # handful of DLC-scaling hotfixes, false now that "Faster animations" added 462 of them.
    # MEASURED: every one of the 32 distinct packages those touch is content-scoped - a DLC
    # prefix (GD_Aster_*, GD_Orchid_*, GD_Sage_*, GD_Anemone_*, GD_Nasturtium_*, GD_Allium_*,
    # GD_Iris_*, GD_Z3_*), a machine type that only exists in some rooms (gd_slotmachine,
    # GD_GameSystemMachines), or base loot content not loaded from the main menu or a room
    # with no chests (GD_Balance_Treasure, Anim_Lootables). There is no subset of these safe
    # to demand from an arbitrary map the way the character skills above are.
    #
    # What core.py actually promises a level=None hotfix is not "resolves from here" - it is
    # "gets resent on every level load, forever" (on_character_live, core.py:320-343), reaching
    # whichever map happens to have the matching content loaded, same as a map-gated hotfix
    # reaches its one named map. A single map can only ever show a slice of that. The honest
    # thing to assert from one map is that the pipeline reaches SOME real objects (not zero -
    # that would mean resolution is broken outright) and that nothing it lands on reads back
    # wrong, which is WRONG/LOOKED_AT below and already covers hotfixes and commands alike.
    _hotfix_total = len(EVERYWHERE) - _CMDS_COUNT
    check(
        "at least some level=None hotfixes resolve from wherever this runs, so the pipeline "
        "reaches real objects instead of only ever naming ones that never exist",
        _hotfix_total > 0 and len(HOTFIX_MISSING) < _hotfix_total,
        f"{_hotfix_total - len(HOTFIX_MISSING)} of {_hotfix_total} level=None hotfixes "
        f"resolve from this map; the other {len(HOTFIX_MISSING)} name objects in content this "
        "map does not load (a different DLC, a machine type not nearby) and are expected to "
        f"stay unresolved until a map that does load them: {HOTFIX_MISSING[:3]}",
    )

    # WRONG is the one that matters: a target that reads back something other than what the
    # command asked for means the command did not land. UNKNOWN is a target whose property this
    # file has no way to compare - an empty tuple, a struct, an object reference - and Auto
    # Sprint brought a pile of those in (it sets OnBegin to an empty list, and there is no
    # sensible "did that land" for an empty list read back as an empty list).
    check(
        "no extras target reads back something other than what its command asked for",
        not WRONG and LOOKED_AT > 0,
        f"{LOOKED_AT} objects compared, {len(WRONG)} wrong: {WRONG[:3]}",
    )
    if UNKNOWN:
        print(f"   ({len(UNKNOWN)} targets set something this file cannot compare - empty lists "
              f"and structs, mostly from Auto Sprint: {UNKNOWN[:2]})")

    # The audit's version of this asserts len(core._by_level['ice_p']) == 3, which is wrong:
    # the Community Patch runs first (features/__init__.py:22-26) and puts its own Ice_P and
    # SouthernShelf_P commands into the same lists. Membership is the honest test.
    held = [(lvl, c) for lvl, c in GATED if c in core._by_level.get(lvl, [])]
    check(
        "every map-gated extras command was held for its map instead of being thrown away",
        len(GATED) > 0 and len(held) == len(GATED),
        f"{len(held)} of {len(GATED)} held; core._by_level carries "
        f"{len(core._by_level.get('ice_p', []))} commands for ice_p and "
        f"{len(core._by_level.get('southernshelf_p', []))} for southernshelf_p in total",
    )

    # Claim 5. The audit says to assert the property is 0.0. It is neither a float nor zero:
    # the command is `set GD_Globals.General.Globals CostToResetSkillPoints
    # (BaseValueScaleConstant=0.000001)`, which scales the cost to a millionth of itself.
    globals_obj = _resolve("GD_Globals.General.Globals")
    scale = (
        float(globals_obj.CostToResetSkillPoints.BaseValueScaleConstant)
        if globals_obj is not None else -1
    )
    check(
        "free respec scales the respec cost to a millionth of itself, which rounds to nothing",
        abs(scale - 1e-6) < 1e-9,
        f"BaseValueScaleConstant = {scale!r}, not the 0.0 the audit's check expected",
    )

    penalty = _resolve("GD_Balance_Inventory.Commerce.DeathPenaltyCost")
    have = penalty is not None
    multiplier = float(penalty.ValueFormula.Multiplier.BaseValueConstant) if have else -1
    penalty_on = bool(penalty.ValueFormula.bEnabled) if have else False
    check(
        "cheaper dying sets the death penalty to 1% of the money you are carrying",
        abs(multiplier - 0.01) < 1e-6 and penalty_on,
        f"Multiplier.BaseValueConstant = {multiplier!r}, bEnabled = {penalty_on}. The money "
        "actually taken on death is measured in extras-and-scaling-needs-travel.py",
    )

    check(
        "the extras switch set is never None, so the pack never skips the whole file",
        E.wanted_sections() is not None,
        f"wanted_sections() = {sorted(WANTED)}",
    )

    # --- extras: hiding undiscovered missions --------------------------------------------

    controllers = [
        o for o in unrealsdk.find_all("WillowPlayerController")
        if not o.Name.startswith("Default__")
    ]
    flags = [bool(o.bShowUndiscoveredMissions) for o in controllers]
    check(
        "hiding undiscovered missions is set on every player controller that exists",
        bool(controllers) and all(f == (not SAVED_HIDE) for f in flags),
        f"{len(controllers)} controllers, bShowUndiscoveredMissions = {flags}, "
        f"option is {SAVED_HIDE}",
    )

    # Claim 8, written to fail. The description at extras.py:43 promises immediate effect and
    # the only writer is the SpawningProcessComplete hook at extras.py:53-64.
    before = bool(pc().bShowUndiscoveredMissions)
    E.hide_missions.value = not SAVED_HIDE
    after = bool(pc().bShowUndiscoveredMissions)
    E.hide_missions.value = SAVED_HIDE
    check(
        "toggling 'Hide undiscovered missions' takes effect immediately, as its description says",
        after != before,
        f"the flag stayed {before} while the option went {SAVED_HIDE} -> {not SAVED_HIDE}; "
        "nothing writes it until the next SpawningProcessComplete",
    )
    # INVERTED 2026-08-20. This used to assert that NEITHER callback was wired, which was true
    # when it was written and is the bug the check above exists to catch. One of them is wired
    # now, so the assertion has to be the other way round or it fails for the fix.
    check(
        "something is wired to write bShowUndiscoveredMissions when the option changes",
        getattr(E.hide_missions, "on_change_anytime", None) is not None
        or getattr(E.hide_missions, "on_change_while_enabled", None) is not None,
        f"anytime={getattr(E.hide_missions, 'on_change_anytime', None)!r}, "
        f"while_enabled={getattr(E.hide_missions, 'on_change_while_enabled', None)!r}",
    )

    # Claim 9 is the mission LOG's contents, which is a screen. This only asks whether the list
    # behind it can be read at all, so the next person knows whether a screenshot is needed.
    mission_list = None
    why = ""
    try:
        plays = pc().MissionPlaythroughs
        mission_list = list(plays[int(pc().GetCurrentPlaythrough())].MissionList)
    except Exception as ex:
        why = repr(ex)
    check(
        "the mission list can be read off the controller, so what the log shows is checkable "
        "without a screenshot",
        mission_list is not None,
        f"{len(mission_list)} missions on this playthrough" if mission_list is not None
        else f"MissionPlaythroughs unreadable: {why}",
    )

    # --- extras: switches really do gate what is sent ------------------------------------

    _text_fixes_size = sections_in(TEXT).get("Text Fixes", 0)
    E._switches["Text Fixes"].value = False
    off_cmds, off_hot, _ = commands_from(TEXT, E.wanted_sections())
    E._switches["Text Fixes"].value = SAVED_SWITCHES["Text Fixes"]
    check(
        "unticking Text Fixes leaves only the other five extras commands to send",
        # DERIVED. This used to expect 5, the number left when Text Fixes was one of four
        # sections. What has to be true is that unticking one section removes exactly that
        # section's commands and touches nothing else.
        len(off_cmds) + len(off_hot) == (len(CMDS) + len(HOT)) - _text_fixes_size,
        f"{len(off_cmds)} commands + {len(off_hot)} hotfixes with Text Fixes off, against "
        f"{len(CMDS)} + {len(HOT)} with it on; Text Fixes is {_text_fixes_size} commands",
    )

    # --- level scaling -------------------------------------------------------------------

    check(
        "the level scaling constant exists and can be found right now",
        RESOLVER is not None,
        f"{LS.TARGET} -> {RESOLVER!r}",
    )

    check(
        "the live constant matches the slider position the pack is carrying",
        RESOLVER is not None and abs(SAVED_CONSTANT - SAVED_PERCENT / 100) < 1e-5,
        f"ConstantValue {SAVED_CONSTANT!r} against slider {SAVED_PERCENT!r}",
    )

    # Claim 2 as far as it goes. Proving 1.13 is the GAME's own shipped value needs a read
    # before FrontendGFxMovie:Start ever fires - see extras-and-scaling-needs-travel.py, PHASE 0.
    check(
        "the hard-coded vanilla percent and the slider's own default are the same number",
        LS.VANILLA_PERCENT == 113 and LS.percent.default_value == LS.VANILLA_PERCENT,
        f"VANILLA_PERCENT={LS.VANILLA_PERCENT}, default_value={LS.percent.default_value!r}. "
        "Self-consistency only - nobody here has read the untouched game",
    )

    LS.percent.value = 105
    moved = float(RESOLVER.ConstantValue)
    check(
        "moving the slider writes percent/100 onto the object",
        abs(moved - 1.05) < 1e-5,
        f"slider 105 -> ConstantValue {moved!r}",
    )

    # Claim 4: mods_base/options.py:144-145 calls on_change_anytime BEFORE
    # super().__setattr__ at :155, so the option still reads the old value inside the callback.
    seen = []
    LS.percent.on_change_anytime = lambda option, new: seen.append((option.value, new))
    LS.percent.value = 120
    LS.percent.on_change_anytime = SAVED_CALLBACK
    check(
        "the change callback is handed the new value while the option still reads the old one",
        seen == [(105, 120)],
        f"the callback saw {seen}, expected [(105, 120)]",
    )
    check(
        "a change callback assigned after the option was built really fires",
        len(seen) == 1,
        f"{len(seen)} calls for one assignment",
    )
    check(
        "the slider's callback is on_change_anytime and is the feature's own function",
        LS.percent.on_change_anytime is LS._on_change,
        f"on_change_anytime is {LS.percent.on_change_anytime!r}",
    )

    # Claim 6, REWRITTEN 2026-08-20. It used to assert that reading the value back gave exactly
    # what was written, and then report the failure as the bug - which was the right diagnosis
    # and the wrong test, because the engine stores this as a 32-bit float and no amount of
    # fixing will ever make 1.13 come back as 1.13. The guard was changed to compare within a
    # tolerance instead, so what has to be checked is that the guard FIRES.
    RESOLVER.ConstantValue = 113 / 100
    check(
        "the game stores this as a smaller kind of number, so an exact comparison can never work",
        RESOLVER.ConstantValue != 113 / 100,
        f"wrote {113 / 100!r}, read back {RESOLVER.ConstantValue!r}",
    )
    LS.percent.value = 113
    _before_apply = float(RESOLVER.ConstantValue)
    RESOLVER.ConstantValue = _before_apply
    LS._apply()
    check(
        "re-applying at the same percent leaves the number exactly where it was",
        float(RESOLVER.ConstantValue) == _before_apply,
        f"{_before_apply!r} -> {float(RESOLVER.ConstantValue)!r} - the skip guard compares "
        f"within a tolerance now, so it can actually fire",
    )

    # Claim 11, the half that is still reachable once the patch has already run. The constant is
    # knocked somewhere it could not have got to on its own first, so that "_apply put it back"
    # cannot be confused with "_apply did nothing to a value that was already right".
    LS.percent.value = LS.VANILLA_PERCENT
    RESOLVER.ConstantValue = 1.5
    LS._apply()
    now = float(RESOLVER.ConstantValue)
    check(
        "applying at the shipped 113 puts the constant on the game's own 1.13 and nowhere else",
        abs(now - 1.13) < 1e-5,
        f"knocked to 1.5, _apply() left {now!r}",
    )

    # --- level scaling: does the number actually move gear? ------------------------------

    pool = None
    try:
        pool = unrealsdk.find_object("ItemPoolDefinition", G.POOLS[("weapon", 3)])
    except Exception:
        pool = None

    def _damage(weapon):
        try:
            return float(weapon.InstantHitDamage)
        except Exception:
            return 0.0

    def _batch(count, stage):
        made = []
        for _ in range(count):
            made.extend(G._spawn_from_pool(pc(), pool, stage))
        return made

    if pool is None:
        check(
            "the rare weapon pool the scaling test spawns from can be found",
            False,
            f"no ItemPoolDefinition at {G.POOLS[('weapon', 3)]}",
        )
    else:
        # Twelve of each, not fifty: every spawn happens inside one frame, and 1.13^49 against
        # 1.02^49 is a hundredfold gap - a dozen samples separate that with room to spare.
        RESOLVER.ConstantValue = 1.13
        strong = _batch(12, 50)
        strong_damage = sorted(d for d in (_damage(w) for w in strong) if d > 0)
        witness = next((w for w in strong if _damage(w) > 0), None)
        witness_before = _damage(witness) if witness is not None else 0.0

        RESOLVER.ConstantValue = 1.02
        witness_after = _damage(witness) if witness is not None else 0.0
        weak = _batch(12, 50)
        weak_damage = sorted(d for d in (_damage(w) for w in weak) if d > 0)

        # One line of raw evidence, so a run that measures zero is diagnosable without a second
        # trip: if InstantHitDamage is the wrong field to read, this is where that shows.
        if strong:
            try:
                worth = strong[0].GetMonetaryValue()
            except Exception as ex:
                worth = f"unreadable: {ex!r}"
            print(f"   sample weapon: InstantHitDamage={_damage(strong[0])!r} value={worth!r}")

        mid_strong = strong_damage[len(strong_damage) // 2] if strong_damage else 0.0
        mid_weak = weak_damage[len(weak_damage) // 2] if weak_damage else 0.0
        check(
            "a weapon made at the same game stage comes out weaker when the constant is lowered",
            bool(strong_damage) and bool(weak_damage) and mid_weak < mid_strong * 0.5,
            f"median damage {mid_strong:.0f} at 113% against {mid_weak:.0f} at 102%, stage 50, "
            f"{len(strong_damage)} and {len(weak_damage)} weapons sampled",
        )
        check(
            "a weapon that already exists keeps its numbers when the constant changes afterwards",
            witness is not None and witness_before == witness_after,
            f"the same weapon read {witness_before!r} at 113% and {witness_after!r} at 102%",
        )

finally:
    # A leaked slider or a leaked callback is worse than a failed check: everything that spawns
    # for the rest of the session would carry whatever number was left behind.
    try:
        LS.percent.on_change_anytime = SAVED_CALLBACK
        LS.percent.value = SAVED_PERCENT
    except Exception as ex:
        print(f"   COULD NOT restore the slider: {ex!r}")
    try:
        if RESOLVER is not None and SAVED_CONSTANT is not None:
            RESOLVER.ConstantValue = SAVED_CONSTANT
    except Exception as ex:
        print(f"   COULD NOT restore the scaling constant: {ex!r}")
    E.hide_missions.value = SAVED_HIDE
    for _name, _was in SAVED_SWITCHES.items():
        E._switches[_name].value = _was
    try:
        _now = RESOLVER.ConstantValue if RESOLVER is not None else None
    except Exception as ex:
        _now = f"unreadable: {ex!r}"
    print(
        f"   restored: slider {LS.percent.value!r}, constant {_now!r}, "
        f"hide_missions {E.hide_missions.value!r}, switches "
        f"{[o.value for o in E._switches.values()]}",
    )

summary()
