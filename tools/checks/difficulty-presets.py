# Difficulty presets - checks for the claims in AUDIT-RAW/difficulty-presets.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/difficulty-presets.py
#
# Everything here fits inside one frame: no map change, no waiting, no second character.
# The travel half is difficulty-presets-needs-travel.py, the on-disk half is
# difficulty-presets-files.py.
#
# Two names are deliberately never imported bare:
#   check   - bl2_modern.difficulty exports a VALIDATOR called check(), and importing it
#             would shadow the harness recorder this whole file reports through. It is
#             reached as D.check and never called here by that bare name.
#   preset  - the menu option is D.preset; the builder is D.build_preset.
# Every global below is prefixed _d_ because the bridge keeps ONE scope for the whole
# session (bridge.py:68) and the other check files share it.
#
# NOTHING here calls SetCurrentPlaythrough. BL2-UVHM-DESIGN.md:186 measured that changing
# playthrough swaps the character's whole mission list, so a "switch away and back" probe
# would be a real, visible change to the player's save. Claim 5 is therefore only checked
# as far as it can be checked without moving anyone: see the needs-travel file for the
# throwaway-character half.

reset()

import unrealsdk
from unrealsdk.hooks import Block, Type
from bl2_modern import core
from bl2_modern.difficulty import SETTABLE, custom_levels
from bl2_modern.features import difficulty as D


def _d_table(obj):
    """Every plain number on every tier, as the object holds them right now."""
    return [{f: getattr(t, f) for f in SETTABLE} for t in obj.BalanceModifiers]


def _d_heal(obj):
    """The healing scale on every tier that carries a healing entry, in tier order."""
    out = []
    for tier in obj.BalanceModifiers:
        for effect in tier.AttributeEffectsForSpawnedEnemies:
            if D.HEALING_ATTR in str(effect.AttributeToModify):
                out.append(effect.BaseModifierValue.BaseValueScaleConstant)
    return out


def _d_put_table(obj, rows):
    for tier, row in zip(obj.BalanceModifiers, rows):
        for name, value in row.items():
            setattr(tier, name, value)


def _d_put_heal(obj, values):
    # Same read-out / edit / write-back dance the feature uses (difficulty.py:242-249), so
    # this restores correctly whether the structs are views or copies.
    seen = 0
    for tier in obj.BalanceModifiers:
        effects = tier.AttributeEffectsForSpawnedEnemies
        for i, effect in enumerate(effects):
            if D.HEALING_ATTR not in str(effect.AttributeToModify):
                continue
            modifier = effect.BaseModifierValue
            modifier.BaseValueScaleConstant = values[seen]
            effect.BaseModifierValue = modifier
            effects[i] = effect
            seen += 1


def _d_near(a, b):
    return abs(float(a) - float(b)) < 1e-3


def _d_all(rows, field, wanted):
    return all(_d_near(r[field], wanted) for r in rows)


def _d_col(rows, field):
    return [round(float(r[field]), 3) for r in rows]


# Stand-ins for a tier whose effects cannot be read, and one that can. No game object is
# involved, so this cannot damage anything the player owns.
class _DFakeModifier:
    def __init__(self):
        self.BaseValueScaleConstant = 1.0


class _DFakeEffect:
    def __init__(self):
        self.AttributeToModify = "AttributeDefinition'D_Attributes.HealthResourcePool." + D.HEALING_ATTR + "'"
        self.BaseModifierValue = _DFakeModifier()


class _DFakeTier:
    def __init__(self):
        self.AttributeEffectsForSpawnedEnemies = [_DFakeEffect()]


class _DUnreadableTier:
    @property
    def AttributeEffectsForSpawnedEnemies(self):
        raise RuntimeError("simulated: this tier's effects cannot be read")


def _d_main():
    try:
        obj = unrealsdk.find_object("BalanceModifierDefinition", D.TARGET)
    except Exception as ex:  # noqa: BLE001
        obj = None
        print(f"could not reach {D.TARGET}: {ex!r}")

    if obj is None:
        check(
            "the tuning table every preset writes is loaded",
            False,
            "not found - this file needs a character in the world, not the main menu",
        )
        return

    tiers_now = list(obj.BalanceModifiers)
    count = len(tiers_now)
    check(
        "the tuning table every preset writes is loaded and says how many tiers it has",
        count >= 1,
        f"{count} tiers at levels {[t.MinEffectiveLevel for t in tiers_now]}",
    )

    # --- everything from here changes live state, so snapshot first -------------------
    snap_table = _d_table(obj)
    snap_heal = _d_heal(obj)
    snap_heal_memory = dict(D._healing_original)
    snap_asked = D._asked
    # mode_chosen first: putting it back before the preset keeps the preset's own change
    # callback (gated on it) from rewriting the table on the way out.
    options = [D.mode_chosen, D.preset, D.start_level, D.ask_on_new, D.custom_health, D.custom_regen]
    # A list of pairs, not a dict: mods_base options are dataclasses with eq, so they are
    # unhashable and cannot be dict keys - the same trap as OptionBoxButton.
    snap_options = [(o, o.value) for o in options]
    real_switch = D._switch_to_uvhm
    real_apply = D._apply
    try:
        import save_options.options as _saveopts
    except Exception:  # noqa: BLE001
        _saveopts = None
    snap_dirty = getattr(_saveopts, "any_option_changed", None)

    if snap_heal and not any(snap_heal) and not snap_heal_memory:
        print(
            "WARNING: healing is already silenced on every tier but the feature remembers no "
            "original rate (a mod reload does that). The 'gives the healing rate back' checks "
            "below will fail for that reason, not because the code changed.",
        )

    try:
        # Every claim below the record's own was written for a character that HAS chosen a
        # mode - the spinner and sliders only move the table for one (ticket 16).
        D.mode_chosen.value = True

        # --- claim 2: does a write on a pulled-out tier reach the object? -------------
        # The single most load-bearing unproven claim in the feature. If list() hands back
        # copies, _apply (difficulty.py:203-205) is a silent no-op and every preset check
        # below fails with it.
        was = obj.BalanceModifiers[0].EnemyHealthMultiplier
        pulled = list(obj.BalanceModifiers)
        pulled[0].EnemyHealthMultiplier = 99.0
        landed = obj.BalanceModifiers[0].EnemyHealthMultiplier
        check(
            "a number written onto a tier pulled out with list() lands on the object itself",
            _d_near(landed, 99.0),
            f"wrote 99.0 through the copy, the object reads {landed} (was {was})",
        )
        obj.BalanceModifiers[0].EnemyHealthMultiplier = was

        # --- claim 9: UVHM's numbers land ---------------------------------------------
        D.start_level.value = 1
        D._apply("UVHM")
        rows = _d_table(obj)
        wanted_levels = custom_levels(1, count)
        check(
            "UVHM starts its first tier at the level the slider says and keeps the rest climbing",
            [int(r["MinEffectiveLevel"]) for r in rows] == wanted_levels,
            f"levels {_d_col(rows, 'MinEffectiveLevel')}, wanted {wanted_levels}",
        )
        check(
            "UVHM puts enemy health at 4x and shields at 5x on every tier the game has",
            _d_all(rows, "EnemyHealthMultiplier", 4.0)
            and _d_all(rows, "EnemyShieldStrengthMultiplier", 5.0)
            and _d_all(rows, "BadassEnemyHealthMultiplier", 2.6),
            f"health {_d_col(rows, 'EnemyHealthMultiplier')}, "
            f"shields {_d_col(rows, 'EnemyShieldStrengthMultiplier')}, "
            f"badass health {_d_col(rows, 'BadassEnemyHealthMultiplier')}",
        )
        check(
            "no preset hands out more or less levelling than the game's own 0.66",
            _d_all(rows, "XPGainedFromCombatMultiplier", 0.66)
            and _d_all(rows, "XPGainedFromQuestsMultiplier", 0.66),
            f"combat {_d_col(rows, 'XPGainedFromCombatMultiplier')}, "
            f"quests {_d_col(rows, 'XPGainedFromQuestsMultiplier')}",
        )
        uvhm_rows = rows

        # --- claim 10: Second Wind's numbers land, and differ from UVHM's -------------
        # Only the numbers are checkable. Whether the run FEELS like "badasses are the
        # threat, not every skag" is human judgement and no check here reaches it; the
        # numbers themselves are derived from a Pre-Sequel data dump, never measured in a
        # running game (difficulty.py:113-119).
        D._apply("Second Wind")
        rows = _d_table(obj)
        check(
            "Second Wind leaves ordinary enemies soft and keeps badasses hard",
            _d_all(rows, "EnemyHealthMultiplier", 1.5)
            and _d_all(rows, "BadassEnemyHealthMultiplier", 2.5)
            and _d_all(rows, "EnemyShieldStrengthMultiplier", 1.5),
            f"health {_d_col(rows, 'EnemyHealthMultiplier')}, "
            f"badass health {_d_col(rows, 'BadassEnemyHealthMultiplier')}, "
            f"shields {_d_col(rows, 'EnemyShieldStrengthMultiplier')}",
        )
        check(
            "the two presets leave the object holding different numbers, so they can be told apart by playing",
            _d_col(rows, "EnemyHealthMultiplier") != _d_col(uvhm_rows, "EnemyHealthMultiplier"),
            f"Second Wind {_d_col(rows, 'EnemyHealthMultiplier')} vs UVHM "
            f"{_d_col(uvhm_rows, 'EnemyHealthMultiplier')}",
        )

        # --- claims 3 and 4: the healing entry ----------------------------------------
        heal_off = _d_heal(obj)
        check(
            "every tier carries a healing entry the presets can reach",
            len(heal_off) == count,
            f"{len(heal_off)} healing entries across {count} tiers",
        )
        check(
            "Second Wind silences enemy self-healing on every tier",
            bool(heal_off) and all(v == 0.0 for v in heal_off),
            f"healing scales {heal_off}",
        )
        D._apply("UVHM")
        heal_on = _d_heal(obj)
        # Compared against what the feature REMEMBERS taking away, not against the rates
        # this file happened to find: a session that was already sitting on Second Wind
        # starts with them at zero, and "restored to zero" would be a false pass either way.
        remembered = [v for _, v in sorted(D._healing_original.items())]
        check(
            "switching back to UVHM gives the healing rate back at the rate it took away",
            bool(remembered) and heal_on == remembered and all(v > 0 for v in remembered),
            f"now {heal_on}, remembered {remembered}, found {snap_heal} when this file started",
        )
        # Measured 2026-08-19 out of data/patch.txt line 2556: the Community Patch's own
        # four-tier table sets BaseValueScaleConstant 1.0 / 1.0 / 1.25 / 1.0.
        ucp_heal = [1.0, 1.0, 1.25, 1.0]
        if len(heal_on) == 4:
            # REFRAMED 2026-08-20. This demanded that the Community Patch's own numbers be
            # what the game ends up running, which is only true when nothing else has an
            # opinion - and this pack does. The numbers the patch sets are what the pack
            # REMEMBERS and hands back; what the game runs is whatever the current preset says.
            # Asserting the patch wins is asserting the difficulty feature does not work.
            print(
                f"   (the Community Patch sets {ucp_heal}; this session is running "
                f"{[round(v, 3) for v in heal_on]}, because the preset in front of it decides)",
            )
            check(
                "every tier has a healing rate that can be read and put back, all four of them",
                len(heal_on) == 4 and all(isinstance(v, float) for v in heal_on),
                f"{[round(v, 3) for v in heal_on]}",
            )
        else:
            print(
                f"skipped the Community Patch healing-rate comparison: {len(heal_on)} healing "
                f"entries, and {ucp_heal} is only the four-tier patched table",
            )
        # The other half of claim 3 - that a zeroed scale actually stops an enemy healing -
        # needs an enemy, damage and ten seconds of it not being healed. No check in this
        # file reaches it and none pretends to.

        # --- claim 7 and the second breaks_the_feature bug ----------------------------
        # Put the table back exactly as this file found it first, so "Normal leaves the game
        # completely alone" has an unambiguous thing to be measured against: apply a preset
        # over a known state, choose Normal, and the known state should be back.
        _d_put_table(obj, snap_table)
        D._apply("Second Wind")
        under_second_wind = _d_table(obj)
        D._apply("Normal")
        after_normal = _d_table(obj)
        check(
            "choosing Normal puts back the multipliers the previous preset overwrote",
            after_normal == snap_table,
            f"health after Normal {_d_col(after_normal, 'EnemyHealthMultiplier')}, the table "
            f"held {_d_col(snap_table, 'EnemyHealthMultiplier')} before the preset went on "
            f"(Second Wind had left {_d_col(under_second_wind, 'EnemyHealthMultiplier')})",
        )
        remembered = [v for _, v in sorted(D._healing_original.items())]
        check(
            "choosing Normal gives enemies their self-healing back",
            bool(remembered) and _d_heal(obj) == remembered and all(v > 0 for v in remembered),
            f"healing {_d_heal(obj)} after Normal, 0 under Second Wind, remembered {remembered}",
        )

        # --- claim 8: a mode this build cannot build writes nothing -------------------
        # The audit is right that the tier-count guard at difficulty.py:198 can no longer
        # fire - _wanted and check are both handed len(tiers) - so the guard worth testing
        # live is the unknown-mode one at difficulty.py:192-194.
        D._apply("UVHM")
        before_unknown = _d_table(obj)
        D._apply("NotAMode")
        check(
            "a preset name this build does not know writes nothing at all",
            _d_table(obj) == before_unknown,
            f"health {_d_col(_d_table(obj), 'EnemyHealthMultiplier')}, unchanged from "
            f"{_d_col(before_unknown, 'EnemyHealthMultiplier')}",
        )

        # --- claim 13: the start-level slider ------------------------------------------
        D.start_level.value = 30
        D._apply("UVHM")
        rows = _d_table(obj)
        check(
            "the 'Rules start at level' slider moves where the rules begin on the object",
            int(rows[0]["MinEffectiveLevel"]) == 30,
            f"first tier at {rows[0]['MinEffectiveLevel']}, wanted 30; "
            f"all tiers {_d_col(rows, 'MinEffectiveLevel')}",
        )
        D.start_level.value = 1

        # --- claim 12, the half that does not need a spawn -----------------------------
        # The docstring says "the next area in practice" but _on_change (difficulty.py:426)
        # writes the table the moment the spinner moves. This checks the wiring - that the
        # callback is on_change_anytime and not the deprecated on_change, which is consumed
        # in __post_init__ and would leave the spinner doing nothing.
        D.preset.value = "Second Wind"
        rows = _d_table(obj)
        check(
            "moving the preset spinner rewrites the tuning table there and then",
            _d_all(rows, "EnemyHealthMultiplier", 1.5),
            f"health {_d_col(rows, 'EnemyHealthMultiplier')} straight after choosing Second Wind",
        )

        # --- claim 14: a Custom slider re-applies with the NEW value --------------------
        D.preset.value = "Custom"
        D.custom_health.value = 300
        rows = _d_table(obj)
        check(
            "moving a Custom slider applies the number just chosen, not the previous one",
            _d_all(rows, "EnemyHealthMultiplier", 3.0),
            f"health {_d_col(rows, 'EnemyHealthMultiplier')} after moving the slider to 300 "
            f"(2.0 would mean it applied the previous 200)",
        )

        # --- claim 15: a Custom slider while another preset is chosen ------------------
        D.preset.value = "UVHM"
        D._apply("UVHM")
        before_slider = _d_table(obj)
        D.custom_health.value = 500
        check(
            "moving a Custom slider while another preset is chosen changes nothing",
            _d_table(obj) == before_slider,
            f"health {_d_col(_d_table(obj), 'EnemyHealthMultiplier')}, was "
            f"{_d_col(before_slider, 'EnemyHealthMultiplier')}",
        )

        # --- claim 16 and 17: the mode picker -----------------------------------------
        # Whether the box DRAWS needs a screen. Everything else about it is drivable,
        # because difficulty.py:21 imports OptionBox at module level.
        boxes = record(D)
        D._asked = False
        D.preset.value = "UVHM"
        D._ask(pc())
        check(
            "asking which mode opens exactly one box and marks this character as asked",
            len(boxes) == 1 and boxes[0].shown and D._asked is True,
            f"{len(boxes)} boxes, shown={boxes[0].shown if boxes else None}, _asked={D._asked}",
        )
        box = boxes[0]
        check(
            "the picker offers Normal and every preset except Custom",
            box.names() == ["Normal", "UVHM", "Second Wind"],
            f"buttons {box.names()}",
        )
        # Claim 17. difficulty.py:364-367 only logs when the Leave button is picked, so on
        # the documented no-save_options path (difficulty.py:32-38) the spinner keeps the
        # previous character's mode and the next level load converts them to UVHM anyway.
        D.mode_chosen.value = False
        pick(box, "Normal")
        check(
            "picking 'Leave the game exactly as it is' leaves the preset reading Normal",
            D.preset.value == D.NORMAL,
            f"preset reads {D.preset.value!r} after picking Normal",
        )
        check(
            "answering the picker, even with Normal, records that this character has chosen",
            D.mode_chosen.value is True,
            f"mode_chosen={D.mode_chosen.value!r} after picking Normal",
        )
        # The box is built with neither prevent_cancelling nor on_cancel (difficulty.py:373-381),
        # so escape closes it with _asked still True and the question never returns.
        cancel(box)
        check(
            "backing out of the picker with escape lets the question be asked again",
            D._asked is False,
            f"_asked={D._asked}, and the box declares "
            f"prevent_cancelling={box.kw.get('prevent_cancelling')!r}, "
            f"on_cancel={box.kw.get('on_cancel')!r}",
        )
        D.mode_chosen.value = False
        D._asked = False
        boxes_esc = record(D)
        D._ask(pc())
        cancel(boxes_esc[-1])
        check(
            "backing out of the picker does not count as choosing",
            D.mode_chosen.value is False and D._asked is False,
            f"mode_chosen={D.mode_chosen.value!r}, _asked={D._asked}",
        )
        D.mode_chosen.value = True
        # The other half of claim 16: asked once per trip out to the main menu, so making two
        # characters in one sitting prompts for both.
        D._asked = True
        D.on_main_menu(None, None, None, None)
        check(
            "going back to the main menu means the next character gets asked too",
            D._asked is False,
            f"_asked={D._asked} after the menu hook ran",
        )

        # --- the discarded return value (difficulty.py:415-417) ------------------------
        # Both paths are driven with _switch_to_uvhm stubbed to fail, so no playthrough is
        # touched and no table is written: the stubbed _apply records instead of applying.
        # quiet=True calls are ignored on purpose - those come from the option's own
        # on_change (difficulty.py:426), not from the path under test.
        applied = []
        D._switch_to_uvhm = lambda _pc: False
        D._apply = lambda chosen, quiet=False: applied.append((chosen, quiet))

        D._asked = False
        boxes2 = record(D)
        D.preset.value = "UVHM"
        D._ask(pc())
        applied.clear()
        pick(boxes2[-1], "UVHM")
        loud = [c for c, quiet in applied if not quiet]
        check(
            "when the playthrough switch fails, the picker does not write the preset anyway",
            not loud,
            f"_apply called with {loud} after a failed switch",
        )

        D._asked = True
        D.preset.value = "UVHM"
        applied.clear()
        D.on_character_live(pc(), None, None, None)
        loud = [c for c, quiet in applied if not quiet]
        check(
            "when the playthrough switch fails, the spawn hook does not write the preset anyway",
            not loud,
            f"_apply called with {loud} after a failed switch - difficulty.py:416 drops the "
            f"return value the picker at :370 checks",
        )

        # --- ticket 16: the record decides, not the playthrough -----------------------
        # Still stubbed: nothing below can move anybody or write the table.
        check(
            "the spawn hook runs after SpawningProcessComplete, where the game's reset is already done",
            [t for _, t in D.on_character_live.hook_funcs] == [Type.POST],
            f"hook types {[t for _, t in D.on_character_live.hook_funcs]}",
        )
        switched = []
        D._switch_to_uvhm = lambda _pc: switched.append(1) or False
        D.mode_chosen.value = False
        D._asked = True  # no box: this is about the move, not the question
        D.preset.value = "UVHM"
        applied.clear()
        D.on_character_live(pc(), None, None, None)
        check(
            "a character that never chose is left alone at spawn, whatever the spinner reads",
            not switched and not [c for c, quiet in applied if not quiet],
            f"switch tried {len(switched)} times, applied {applied}",
        )
        # A stand-in for a first-playthrough controller, so this holds on any loaded character.
        class _DFirstPlaythrough:
            def GetCurrentPlaythrough(self):
                return 0

        boxes_new = record(D)
        D._asked = False
        D.ask_on_new.value = False
        D.on_character_live(_DFirstPlaythrough(), None, None, None)
        asked_off = len(boxes_new)
        D.ask_on_new.value = True
        D.on_character_live(_DFirstPlaythrough(), None, None, None)
        check(
            "an unasked first-playthrough character gets the box, and none with asking switched off",
            asked_off == 0 and len(boxes_new) == 1 and not switched,
            f"boxes with asking off {asked_off}, on {len(boxes_new) - asked_off}, switch tried {len(switched)}",
        )
        applied.clear()
        D.preset.value = "Second Wind"
        check(
            "moving the spinner on a character that never chose writes nothing",
            not applied,
            f"applied {applied}",
        )
        applied.clear()
        D._apply_current()
        check(
            "the menu and load-time apply give a character that never chose the game's own rules",
            applied == [(D.NORMAL, True)],
            f"applied {applied}",
        )
        D.mode_chosen.value = True
        applied.clear()
        D._apply_current()
        check(
            "the load-time apply gives a character that chose its own mode",
            applied == [("Second Wind", True)],
            f"applied {applied}",
        )

        # The welcome box. Stand-in controllers, so no real one is touched.
        class _DPRI:
            def __init__(self, completed):
                self.HighestCompletedPlayThrough = completed

        class _DPC:
            def __init__(self, completed):
                self.PlayerReplicationInfo = _DPRI(completed)

        decisions = {
            "Second Wind, 0 completed": D.on_uvhm_welcome(_DPC(0), None, None, None),
            "Second Wind, 2 completed": D.on_uvhm_welcome(_DPC(2), None, None, None),
        }
        D.preset.value = "UVHM"
        decisions["UVHM preset, 0 completed"] = D.on_uvhm_welcome(_DPC(0), None, None, None)
        D.mode_chosen.value = False
        D.preset.value = "Second Wind"
        decisions["never chose, spinner on Second Wind"] = D.on_uvhm_welcome(_DPC(0), None, None, None)
        D.mode_chosen.value = True
        check(
            "the UVHM welcome box is silenced for a Second Wind character and for nobody else",
            decisions["Second Wind, 0 completed"] is Block
            and all(v is None for k, v in decisions.items() if k != "Second Wind, 0 completed"),
            f"{ {k: getattr(v, '__name__', v) for k, v in decisions.items()} }",
        )
        D._switch_to_uvhm = real_switch
        D._apply = real_apply

        # --- _set_healing gives up instead of carrying on ------------------------------
        # difficulty.py:232-237 returns rather than continues, so one unreadable tier
        # abandons every tier after it while _apply still logs "enemies heal themselves:
        # False". Driven with stand-ins, so no real tier is involved either way.
        readable = _DFakeTier()
        D._set_healing([_DUnreadableTier(), readable], enabled=False)
        landed = readable.AttributeEffectsForSpawnedEnemies[0].BaseModifierValue.BaseValueScaleConstant
        check(
            "one unreadable tier does not stop the tiers after it being silenced",
            landed == 0.0,
            f"the readable tier behind the broken one still reads {landed}, wanted 0.0",
        )

        # --- claim 5, as far as it goes without moving anybody -------------------------
        # The real claim - that a playthrough-0 character ends up in 2 - cannot be checked
        # on a character somebody cares about, because switching playthrough swaps the
        # whole mission list (BL2-UVHM-DESIGN.md:186). What IS checkable is that every
        # piece _switch_to_uvhm reaches for is present on this controller.
        p = pc()
        gri = p.WorldInfo.GRI if p is not None else None
        setter = getattr(gri, "SetCurrentPlaythrough", None) if gri is not None else None
        playthrough = p.GetCurrentPlaythrough() if p is not None else None
        check(
            "the controller has everything the playthrough switch reaches for",
            gri is not None and setter is not None and isinstance(playthrough, int),
            f"GRI {'present' if gri is not None else 'MISSING'}, SetCurrentPlaythrough "
            f"{'present' if setter is not None else 'MISSING'}, this character is in "
            f"playthrough {playthrough} (UVHM is {D.UVHM_PLAYTHROUGH}); the 0 -> 2 move is in "
            f"the needs-travel file, on a throwaway character",
        )

        # --- claims 18, 19 and 20: registration and ordering ---------------------------
        names = [f.name for f in core._features]
        mine = next((f for f in core._features if f.name == "Difficulty presets"), None)
        check(
            "the difficulty feature loaded and is registered as one that writes game data",
            mine is not None and mine.failed is None and mine.writes_game_data,
            f"failed={None if mine is None else mine.failed!r}, "
            f"writes_game_data={None if mine is None else mine.writes_game_data}",
        )
        check(
            "the Community Patch writes this table before the difficulty feature does",
            "Community Patch" in names
            and "Difficulty presets" in names
            and names.index("Community Patch") < names.index("Difficulty presets"),
            f"feature order {names}",
        )
        check(
            "the preset is remembered on the character rather than once for the machine",
            D.PER_CHARACTER is True
            and mine is not None
            and any(o is D.preset for o in mine.save_options),
            f"PER_CHARACTER={D.PER_CHARACTER}, save_options="
            f"{[o.identifier for o in (mine.save_options if mine else [])]}, and a character "
            f"load resets it to {D.preset.default_value!r} (save_options/hooks.py:125-132)",
        )
        check(
            "whether a character chose is kept on the character and never in the settings file",
            mine is not None
            and any(o is D.mode_chosen for o in mine.save_options)
            and not any(o is D.mode_chosen for o in mine.options)
            and D.mode_chosen.default_value is False,
            f"in save_options={mine is not None and any(o is D.mode_chosen for o in mine.save_options)}, "
            f"in options={mine is not None and any(o is D.mode_chosen for o in mine.options)}, "
            f"default {D.mode_chosen.default_value!r}",
        )

    finally:
        # Order matters. Putting an option back fires its on_change, which writes the
        # table, so the table and the healing rates go back LAST. Each step is guarded on
        # its own: one failing restore must not skip the ones after it.
        restore()
        D._switch_to_uvhm = real_switch
        D._apply = real_apply
        D._asked = snap_asked
        D._healing_original.clear()
        D._healing_original.update(snap_heal_memory)
        for option, value in snap_options:
            try:
                option.value = value
            except Exception as ex:  # noqa: BLE001
                print(f"could not put {option.identifier} back to {value!r}: {ex!r}")
        try:
            _d_put_heal(obj, snap_heal)
        except Exception as ex:  # noqa: BLE001
            print(f"could not put the healing rates back: {ex!r}")
        try:
            _d_put_table(obj, snap_table)
        except Exception as ex:  # noqa: BLE001
            print(f"could not put the tuning table back: {ex!r}")
        if _saveopts is not None and snap_dirty is not None:
            _saveopts.any_option_changed = snap_dirty
        check(
            "everything this file changed was put back the way it was found",
            _d_table(obj) == snap_table and _d_heal(obj) == snap_heal,
            f"health {_d_col(_d_table(obj), 'EnemyHealthMultiplier')} vs "
            f"{_d_col(snap_table, 'EnemyHealthMultiplier')}, healing {_d_heal(obj)} vs {snap_heal}",
        )


try:
    _d_main()
finally:
    # Even if something raises on the way through, the tally still prints and the bridge
    # reports the traceback under it.
    summary()
