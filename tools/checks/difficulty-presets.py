# Difficulty presets - checks for the claims in AUDIT-RAW/difficulty-presets.md, and ticket 21
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
from unrealsdk.hooks import Block, Type, add_hook, remove_hook
from unrealsdk.unreal import UObject, WrappedArray, WrappedStruct
from bl2_modern import core
from bl2_modern import difficulty as DN
from bl2_modern.difficulty import SETTABLE, custom_levels
from bl2_modern.features import difficulty as D
from bl2_modern.features import difficultyreport as DR
from bl2_modern.patchfile import commands_from


def _d_table(obj):
    """Every plain number on every tier, as the object holds them right now."""
    return [{f: getattr(t, f) for f in SETTABLE} for t in obj.BalanceModifiers]


def _d_effects(obj, list_name, attr):
    """The scale on every matching effect entry, in tier order."""
    out = []
    for tier in obj.BalanceModifiers:
        for effect in getattr(tier, list_name):
            if attr in str(effect.AttributeToModify):
                out.append(effect.BaseModifierValue.BaseValueScaleConstant)
    return out


def _d_heal(obj):
    return _d_effects(obj, "AttributeEffectsForSpawnedEnemies", D.HEALING_ATTR)


def _d_dot(obj):
    return _d_effects(obj, "AttributeEffectsForPlayers", D.DOT_ATTR)


def _d_slag_time(obj):
    return _d_effects(obj, "AttributeEffectsForSpawnedEnemies", D.SLAG_TIME_ATTR)


def _d_put_table(obj, rows):
    for tier, row in zip(obj.BalanceModifiers, rows):
        for name, value in row.items():
            setattr(tier, name, value)


def _d_put_effects(obj, list_name, attr, values):
    # Same read-out / edit / write-back dance the feature uses, so this restores correctly
    # whether the structs are views or copies.
    seen = 0
    for tier in obj.BalanceModifiers:
        effects = getattr(tier, list_name)
        for i, effect in enumerate(effects):
            if attr not in str(effect.AttributeToModify):
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
    return [round(float(r[field]), 4) for r in rows]


def _d_plain(v):
    if isinstance(v, WrappedStruct):
        out = {}
        p = v._type.Children
        while p is not None:
            out[p.Name] = _d_plain(getattr(v, p.Name))
            p = p.Next
        return out
    if isinstance(v, WrappedArray):
        return [_d_plain(x) for x in v]
    if isinstance(v, UObject):
        return v._path_name()
    return v


def _d_slag():
    """Everything the slag switch writes, as plain values."""
    skill = unrealsdk.find_object("SkillDefinition", DN.SLAG_SKILL)
    status = unrealsdk.find_object("StatusEffectDefinition", DN.SLAG_STATUS)
    card = unrealsdk.find_object("AttributePresentationDefinition", DN.SLAG_CARD)
    return {
        "effects": _d_plain(skill.SkillEffectDefinitions),
        "duration": _d_plain(status.BaseDuration),
        "card": str(card.Description),
    }


def _d_split(text, top_level_items):
    """Split the game's text form at depth 0: items of "(a),(b)" or fields of "k=v,k=(...)"."""
    out, depth, cur, start = [], 0, "", None
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
            if top_level_items and depth == 1:
                start = i + 1
        elif ch == ")":
            depth -= 1
            if top_level_items and depth == 0:
                out.append(text[start:i])
        if not top_level_items:
            if ch == "," and depth == 0:
                out.append(cur)
                cur = ""
                continue
            cur += ch
    if not top_level_items and cur:
        out.append(cur)
    return out


def _d_ucp_table():
    """The Community Patch's own table, read from its file - independent of anything the pack remembers."""
    text = (core.Path(core.__file__).parent / "data" / "patch.txt").read_text(encoding="utf-8", errors="replace")
    commands, _, _ = commands_from(text)
    writes = [c for c in commands if f"{DN.TARGET} {DN.PROPERTY}" in c]
    if len(writes) != 1:
        return None
    body = writes[0].split(f" {DN.PROPERTY} ", 1)[1].strip()[1:-1]
    rows = []
    for tier in _d_split(body, True):
        fields = dict(f.partition("=")[::2] for f in _d_split(tier, False))
        rows.append({name: float(fields[name]) for name in SETTABLE if name in fields})
    return rows


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
    snap_dot = _d_dot(obj)
    snap_slag_time = _d_slag_time(obj)
    snap_slag_state = D._slag_state()
    snap_memories = [(m, type(m)(m)) for m in (D._healing_original, D._dot_original, D._slag_time_original, D._table_original)]
    snap_flags = {"_new_character": D._new_character, "PER_CHARACTER": D.PER_CHARACTER}
    snap_chosen_by = dict(D.chosen_by_character.value)
    # mode_chosen first: putting it back before the preset keeps the preset's own change
    # callback (gated on it) from rewriting the table on the way out.
    options = [D.mode_chosen, D.preset, D.start_level, D.ask_on_new, D.custom_health, D.custom_regen]
    # A list of pairs, not a dict: mods_base options are dataclasses with eq, so they are
    # unhashable and cannot be dict keys - the same trap as OptionBoxButton.
    snap_options = [(o, o.value) for o in options]
    real_switch = D._switch_to_uvhm
    real_apply = D._apply
    real_save = D.chosen_by_character.save
    real_guid = D._guid
    try:
        import save_options.options as _saveopts
    except Exception:  # noqa: BLE001
        _saveopts = None
    snap_dirty = getattr(_saveopts, "any_option_changed", None)
    ucp = _d_ucp_table()

    try:
        # Every claim below the record's own was written for a character that HAS chosen a
        # mode - the spinner and sliders only move the table for one (ticket 16).
        D.mode_chosen.value = True

        # --- claim 2: does a write on a pulled-out tier reach the object? -------------
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
            "UVHM keeps the game's own experience rate, 0.66, and its own slag (1.5)",
            _d_all(rows, "XPGainedFromCombatMultiplier", 0.66)
            and _d_all(rows, "XPGainedFromQuestsMultiplier", 0.66)
            and _d_all(rows, "AmplifiedDamageMultiplier", 1.5)
            and D._slag_state() == "game",
            f"combat {_d_col(rows, 'XPGainedFromCombatMultiplier')}, "
            f"quests {_d_col(rows, 'XPGainedFromQuestsMultiplier')}, slag {D._slag_state()}",
        )
        uvhm_rows = rows

        # --- claim 10 (ticket 21): Second Wind's table is target / playthrough 2's own ----
        D._apply("Second Wind")
        rows = _d_table(obj)
        want = dict(zip(
            ("EnemyHealthMultiplier", "BadassEnemyHealthMultiplier", "EnemyShieldStrengthMultiplier",
             "BadassEnemyShieldStrengthMultiplier", "EnemyDamageMultiplier", "XPGainedFromCombatMultiplier",
             "BadassEnemyDamageMultiplier", "XPGainedFromQuestsMultiplier", "AmplifiedDamageMultiplier"),
            (1.0, 1.25, 1.0, 1.75, 0.6686, 0.6, 0.6148, 0.66, 1.0),
        ))
        off = {f: _d_col(rows, f) for f, v in want.items() if not _d_all(rows, f, v)}
        check(
            "Second Wind writes 1.5/2.5/1.5/3.5/1.08/0.66 of Normal divided by playthrough 2's own "
            "1.5/2.0/1.5/2.0/1.62/1.1, and slag at 1.0, on every tier",
            not off,
            f"off target: {off}" if off else f"{len(rows)} tiers: {want}",
        )
        check(
            "the two presets leave the object holding different numbers, so they can be told apart by playing",
            _d_col(rows, "EnemyHealthMultiplier") != _d_col(uvhm_rows, "EnemyHealthMultiplier"),
            f"Second Wind {_d_col(rows, 'EnemyHealthMultiplier')} vs UVHM "
            f"{_d_col(uvhm_rows, 'EnemyHealthMultiplier')}",
        )

        # --- ticket 21: Nifsara's slag, and the Community Patch's player DoT bonus -----------
        sw_slag = _d_slag()
        check(
            "Second Wind puts Nifsara's slag in: no damage bonus, half speed, slower shots, 5 seconds",
            D._slag_state() == "second wind"
            and len(sw_slag["effects"]) == 4
            and [e["BaseModifierValue"]["BaseValueScaleConstant"] for e in sw_slag["effects"][:2]] == [0.0, 0.0]
            and sw_slag["effects"][2]["AttributeToModify"].endswith("FootSpeed")
            and sw_slag["effects"][2]["BaseModifierValue"]["BaseValueConstant"] == -1.0
            and sw_slag["effects"][3]["AttributeToModify"].endswith("WeaponFireInterval")
            and _d_near(sw_slag["effects"][3]["BaseModifierValue"]["BaseValueConstant"], 0.5)
            and sw_slag["duration"]["BaseValueConstant"] == 5.0
            and "half speed" in sw_slag["card"],
            f"state {D._slag_state()}, {len(sw_slag['effects'])} effects, duration {sw_slag['duration']}, "
            f"card {sw_slag['card']!r}",
        )
        dot_sw = _d_dot(obj)
        check(
            "Second Wind takes away the Community Patch's extra burn, corrode and shock damage for players",
            bool(dot_sw) and all(v == 0.0 for v in dot_sw),
            f"player DoT scales {dot_sw}",
        )
        time_sw = _d_slag_time(obj)
        check(
            "Second Wind turns off the entry that doubles slag time on enemies in playthrough 2",
            len(time_sw) == count and all(v == 0.0 for v in time_sw),
            f"slag time scales {time_sw}",
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
        remembered = [v for _, v in sorted(D._healing_original.items())]
        check(
            "switching back to UVHM gives the healing rate back at the rate it took away",
            bool(remembered) and heal_on == remembered and all(v > 0 for v in remembered),
            f"now {heal_on}, remembered {remembered}, found {snap_heal} when this file started",
        )
        dot_back = _d_dot(obj)
        remembered_dot = [v for _, v in sorted(D._dot_original.items())]
        check(
            "switching to UVHM gives players the Community Patch's DoT bonus back",
            bool(remembered_dot) and dot_back == remembered_dot and all(v > 0 for v in remembered_dot),
            f"now {dot_back}, remembered {remembered_dot}",
        )
        time_back = _d_slag_time(obj)
        remembered_time = [v for _, v in sorted(D._slag_time_original.items())]
        check(
            "switching to UVHM gives enemies UVHM's doubled slag time back",
            bool(remembered_time) and time_back == remembered_time and all(v > 0 for v in remembered_time),
            f"now {time_back}, remembered {remembered_time}",
        )

        # --- claim 7 / ticket 24: Normal puts back the table the pack found ------------------
        # Measured against the Community Patch's OWN numbers, read from its file - not against
        # anything the pack remembers and not against whatever this file happened to find, which
        # on a Second Wind character is Second Wind's numbers (the old check passed on that).
        D._apply("Second Wind")
        under_second_wind = _d_table(obj)
        D._apply("Normal")
        after_normal = _d_table(obj)
        if ucp is not None and len(ucp) == count:
            ucp_cols = {f: [r[f] for r in ucp] for f in ucp[0]}
            wrong = {f: (_d_col(after_normal, f), v) for f, v in ucp_cols.items()
                     if [round(x, 4) for x in _d_col(after_normal, f)] != [round(x, 4) for x in v]}
            check(
                "choosing Normal puts back the Community Patch's own table, read from its file",
                not wrong and _d_col(under_second_wind, "EnemyHealthMultiplier") != _d_col(after_normal, "EnemyHealthMultiplier"),
                f"differs: {wrong}" if wrong else
                f"levels {_d_col(after_normal, 'MinEffectiveLevel')}, health {_d_col(after_normal, 'EnemyHealthMultiplier')} "
                f"(Second Wind had {_d_col(under_second_wind, 'EnemyHealthMultiplier')})",
            )
            # And the claim can fail: with the pack's memory emptied, Normal has nothing to put
            # back, and the same comparison has to come out wrong.
            kept = list(D._table_original)
            D._apply("Second Wind")
            D._table_original.clear()
            D._apply("Normal")
            mutant = _d_col(_d_table(obj), "EnemyHealthMultiplier")
            D._table_original.extend(kept)
            D._apply("Normal")
            check(
                "that comparison fails when Normal cannot put the table back (a mutant with no memory)",
                mutant != [round(x, 4) for x in ucp_cols["EnemyHealthMultiplier"]],
                f"with no memory Normal left health at {mutant}; the patch's is {ucp_cols['EnemyHealthMultiplier']}",
            )
        else:
            print(f"skipped the Community Patch comparison: its table was {'not found' if ucp is None else f'{len(ucp)} tiers'}")
            check(
                "choosing Normal puts back the multipliers the pack remembered from before its first write",
                after_normal == D._table_original,
                f"health after Normal {_d_col(after_normal, 'EnemyHealthMultiplier')}",
            )
        remembered = [v for _, v in sorted(D._healing_original.items())]
        check(
            "choosing Normal gives enemies their self-healing back",
            bool(remembered) and _d_heal(obj) == remembered and all(v > 0 for v in remembered),
            f"healing {_d_heal(obj)} after Normal, 0 under Second Wind, remembered {remembered}",
        )
        check(
            "choosing Normal puts the game's own slag back, value for value",
            D._slag_state() == "game" and (snap_slag_state != "game" or _d_slag() == _d_slag_before),
            f"state {D._slag_state()}, card {_d_slag()['card']!r}",
        )

        # --- claim 8: a mode this build cannot build writes nothing -------------------
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
        D.preset.value = "Second Wind"
        rows = _d_table(obj)
        check(
            "moving the preset spinner rewrites the tuning table there and then",
            _d_all(rows, "BadassEnemyHealthMultiplier", 1.25),
            f"badass health {_d_col(rows, 'BadassEnemyHealthMultiplier')} straight after choosing Second Wind",
        )

        # --- ticket 21: the mode is worked out once and follows every change -------------
        D._forget_mode()
        m1 = D._mode()
        D.preset.value = "UVHM"
        m2 = D._mode()
        D.mode_chosen.value = False
        m3 = D._mode()
        D.mode_chosen.value = True
        m4 = D._mode()
        check(
            "the cached mode follows the record and the spinner the moment either changes",
            (m1, m2, m3, m4) == ("Second Wind", "UVHM", "Normal", "UVHM"),
            f"read {m1}, {m2} after the spinner, {m3} with no record, {m4} with it back",
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

        # --- claims 16 and 17: the mode picker -----------------------------------------
        boxes = record(D)
        D.preset.value = "UVHM"
        D._ask(pc())
        check(
            "asking which mode opens exactly one box",
            len(boxes) == 1 and boxes[0].shown,
            f"{len(boxes)} boxes, shown={boxes[0].shown if boxes else None}",
        )
        box = boxes[0]
        check(
            "the picker offers Normal and every preset except Custom",
            box.names() == ["Normal", "UVHM", "Second Wind"],
            f"buttons {box.names()}",
        )
        check(
            "the picker cannot be backed out of: it is asked once and has to be answered",
            box.kw.get("prevent_cancelling") is True and box.kw.get("on_cancel") is None,
            f"prevent_cancelling={box.kw.get('prevent_cancelling')!r}, on_cancel={box.kw.get('on_cancel')!r}",
        )
        D.mode_chosen.value = False
        pick(box, "Normal")
        check(
            "picking 'Leave the game exactly as it is' leaves the preset reading Normal",
            D.preset.value == D.NORMAL,
            f"preset reads {D.preset.value!r} after picking Normal",
        )
        check(
            "answering the picker, even with Normal, records that this character has chosen",
            D.mode_chosen.value is True and D._has_chosen(),
            f"mode_chosen={D.mode_chosen.value!r} after picking Normal",
        )
        D._new_character = True
        D.on_main_menu(None, None, None, None)
        check(
            "going back to the main menu forgets that a new character was being made",
            D._new_character is False,
            f"_new_character={D._new_character}",
        )
        D._new_character = False
        D.on_new_game(None, None, None, None)
        check(
            "the game's new-game notification marks the next spawn as a new character",
            D._new_character is True,
            f"_new_character={D._new_character}",
        )
        D._new_character = False

        # --- the discarded return value ------------------------------------------------
        # Both paths are driven with _switch_to_uvhm stubbed to fail, so no playthrough is
        # touched: the stubbed _apply records instead of applying. quiet=True calls come from
        # the option's own on_change, not the path under test; Normal is allowed (it puts the
        # game's own rules back).
        applied = []
        D._switch_to_uvhm = lambda _pc: False
        D._apply = lambda chosen, quiet=False: applied.append((chosen, quiet))

        boxes2 = record(D)
        D.preset.value = "UVHM"
        D._ask(pc())
        applied.clear()
        pick(boxes2[-1], "UVHM")
        loud = [c for c, quiet in applied if not quiet and c != D.NORMAL]
        check(
            "when the playthrough switch fails, the picker does not write the preset anyway",
            not loud,
            f"_apply called with {applied} after a failed switch",
        )

        D.mode_chosen.value = True
        D.preset.value = "UVHM"
        applied.clear()
        D.on_character_live(pc(), None, None, None)
        loud = [c for c, quiet in applied if not quiet and c != D.NORMAL]
        check(
            "when the playthrough switch fails, the spawn hook does not write the preset anyway",
            not loud,
            f"_apply called with {applied} after a failed switch",
        )

        # --- ticket 16/21: the record decides, and only a new character is asked -----------
        check(
            "the spawn hook runs after SpawningProcessComplete, where the game's reset is already done",
            [t for _, t in D.on_character_live.hook_funcs] == [Type.POST],
            f"hook types {[t for _, t in D.on_character_live.hook_funcs]}",
        )
        switched = []
        D._switch_to_uvhm = lambda _pc: switched.append(1) or False
        D.mode_chosen.value = False
        D._new_character = False
        D.preset.value = "UVHM"
        boxes_old = record(D)
        applied.clear()
        D.on_character_live(pc(), None, None, None)
        check(
            "a character that never chose and was not just made is left alone at spawn: no box, no move",
            not switched and not boxes_old and all(c == D.NORMAL for c, _ in applied),
            f"switch tried {len(switched)} times, {len(boxes_old)} boxes, applied {applied}",
        )
        D._mode_cache = "Second Wind"  # what the last character left behind
        D.on_character_live(pc(), None, None, None)
        check(
            "a spawn forgets the last character's cached mode",
            D._mode() == D.NORMAL,
            f"after the spawn the mode reads {D._mode()!r} for a character that never chose",
        )

        # A stand-in for a first-playthrough controller, like the level-51 Zer0 (playthrough 0,
        # two completed), so this holds on any loaded character.
        class _DFirstPlaythrough:
            def GetCurrentPlaythrough(self):
                return 0

        boxes_zero = record(D)
        D.on_character_live(_DFirstPlaythrough(), None, None, None)
        asked_old = len(boxes_zero)
        D._new_character = True
        D.ask_on_new.value = False
        D.on_character_live(_DFirstPlaythrough(), None, None, None)
        asked_off = len(boxes_zero) - asked_old
        D._new_character = True
        D.ask_on_new.value = True
        D.on_character_live(_DFirstPlaythrough(), None, None, None)
        asked_new = len(boxes_zero) - asked_old - asked_off
        D.on_character_live(_DFirstPlaythrough(), None, None, None)
        asked_again = len(boxes_zero) - asked_old - asked_off - asked_new
        check(
            "only a character just made with New Game gets the box, once, and none with asking off",
            (asked_old, asked_off, asked_new, asked_again) == (0, 0, 1, 0) and not switched,
            f"old playthrough-0 character {asked_old}, asking off {asked_off}, new {asked_new}, "
            f"its next spawn {asked_again}; switch tried {len(switched)}",
        )
        D.ask_on_new.value = True
        D._new_character = False
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

        check(
            "the welcome-box hook runs before the game's check, so its Block can stop the box",
            [t for _, t in D.on_uvhm_welcome.hook_funcs] == [Type.PRE],
            f"hook types {[t for _, t in D.on_uvhm_welcome.hook_funcs]}",
        )
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
        # The review's point 3: it asks once a second in the intro, and must not copy the save
        # each time. Counted by the native every option read goes through.
        reads = {"n": 0}

        def _d_count(*_a):
            reads["n"] += 1

        D._mode()
        add_hook("WillowGame.WillowPlayerController:GetCachedSaveGame", Type.PRE, "d_count", _d_count)
        try:
            for _ in range(5):
                D.on_uvhm_welcome(_DPC(0), None, None, None)
        finally:
            remove_hook("WillowGame.WillowPlayerController:GetCachedSaveGame", Type.PRE, "d_count")
        check(
            "five welcome-box checks read no option and copy no save",
            reads["n"] == 0,
            f"{reads['n']} GetCachedSaveGame calls",
        )
        D._switch_to_uvhm = real_switch
        D._apply = real_apply

        # --- review point 4: without save_options, the answer is kept per character -------
        D.chosen_by_character.save = lambda: None
        D.chosen_by_character.value = {}
        D.PER_CHARACTER = False
        D._switch_to_uvhm = lambda _pc: True
        D._apply = lambda chosen, quiet=False: applied.append((chosen, quiet))
        try:
            D._forget_mode()
            before = (D._has_chosen(), D._mode())
            mine = D._guid()
            D._record("Second Wind")
            D._forget_mode()
            after = (D._has_chosen(), D._mode(), dict(D.chosen_by_character.value))
            D._guid = lambda: "1.2.3.4"
            D._forget_mode()
            other = (D._has_chosen(), D._mode())
        finally:
            D._guid = real_guid
            D.PER_CHARACTER = snap_flags["PER_CHARACTER"]
            D._switch_to_uvhm = real_switch
            D._apply = real_apply
            D.chosen_by_character.value = snap_chosen_by
            D.chosen_by_character.save = real_save
            D._forget_mode()
        check(
            "without save_options an answer is kept under this character's own GUID, and no other character gets it",
            before == (False, "Normal") and after[:2] == (True, "Second Wind") and after[2] == {mine: "Second Wind"}
            and other == (False, "Normal") and bool(mine),
            f"before {before}, after {after}, another character {other}",
        )
        check(
            "the fallback's record is registered only when save_options is missing",
            D.PER_CHARACTER is False or not any(
                o is D.chosen_by_character for f in core._features if f.name == "Difficulty presets" for o in f.options
            ),
            f"PER_CHARACTER={D.PER_CHARACTER}",
        )

        # --- review point 5: the readout names the mode actually played ---------------------
        D.mode_chosen.value = False
        D.preset.value = "Second Wind"
        note_never = DR._preset_note()
        D.mode_chosen.value = True
        note_chose = DR._preset_note()
        check(
            "the difficulty readout says a character that never chose plays Normal, not the spinner's preset",
            "never chose" in note_never and "Second Wind" not in note_never and "Second Wind" in note_chose,
            f"never chose: {note_never.strip()!r}; chose: {note_chose.strip()!r}",
        )

        # --- _set_healing gives up instead of carrying on ------------------------------
        readable = _DFakeTier()
        D._set_healing([_DUnreadableTier(), readable], enabled=False)
        landed = readable.AttributeEffectsForSpawnedEnemies[0].BaseModifierValue.BaseValueScaleConstant
        check(
            "one unreadable tier does not stop the tiers after it being silenced",
            landed == 0.0,
            f"the readable tier behind the broken one still reads {landed}, wanted 0.0",
        )

        # --- claim 5, as far as it goes without moving anybody -------------------------
        p = pc()
        gri = p.WorldInfo.GRI if p is not None else None
        setter = getattr(gri, "SetCurrentPlaythrough", None) if gri is not None else None
        playthrough = p.GetCurrentPlaythrough() if p is not None else None
        check(
            "the controller has everything the playthrough switch reaches for",
            gri is not None and setter is not None and isinstance(playthrough, int),
            f"GRI {'present' if gri is not None else 'MISSING'}, SetCurrentPlaythrough "
            f"{'present' if setter is not None else 'MISSING'}, this character is in "
            f"playthrough {playthrough} (UVHM is {D.UVHM_PLAYTHROUGH})",
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
            f"{[o.identifier for o in (mine.save_options if mine else [])]}",
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
        D.mode_chosen.value = False
        unset = D.mode_chosen._to_json()
        D.mode_chosen.value = True
        check(
            "a character that never chose gets no record written into its save at all",
            unset is ... and D.mode_chosen._to_json() is True,
            f"never chose -> {unset!r}, chose -> {D.mode_chosen._to_json()!r}",
        )

    finally:
        # Order matters. Putting an option back fires its on_change, which writes the
        # table, so the table and the healing rates go back LAST. Each step is guarded on
        # its own: one failing restore must not skip the ones after it.
        restore()
        D._switch_to_uvhm = real_switch
        D._apply = real_apply
        D._guid = real_guid
        D.PER_CHARACTER = snap_flags["PER_CHARACTER"]
        D._new_character = snap_flags["_new_character"]
        D.chosen_by_character.value = snap_chosen_by
        D.chosen_by_character.save = real_save
        for memory, copy in snap_memories:
            memory.clear()
            if isinstance(memory, dict):
                memory.update(copy)
            else:
                memory.extend(copy)
        for option, value in snap_options:
            try:
                option.value = value
            except Exception as ex:  # noqa: BLE001
                print(f"could not put {option.identifier} back to {value!r}: {ex!r}")
        try:
            D._set_slag(second_wind=snap_slag_state == "second wind")
        except Exception as ex:  # noqa: BLE001
            print(f"could not put slag back: {ex!r}")
        for put, values, name in ((("AttributeEffectsForSpawnedEnemies", D.HEALING_ATTR), snap_heal, "healing"),
                                  (("AttributeEffectsForPlayers", D.DOT_ATTR), snap_dot, "player DoT"),
                                  (("AttributeEffectsForSpawnedEnemies", D.SLAG_TIME_ATTR), snap_slag_time, "slag time")):
            try:
                _d_put_effects(obj, put[0], put[1], values)
            except Exception as ex:  # noqa: BLE001
                print(f"could not put the {name} rates back: {ex!r}")
        try:
            _d_put_table(obj, snap_table)
        except Exception as ex:  # noqa: BLE001
            print(f"could not put the tuning table back: {ex!r}")
        D._forget_mode()
        if _saveopts is not None and snap_dirty is not None:
            _saveopts.any_option_changed = snap_dirty
        check(
            "everything this file changed was put back the way it was found",
            _d_table(obj) == snap_table and _d_heal(obj) == snap_heal and _d_dot(obj) == snap_dot
            and _d_slag_time(obj) == snap_slag_time
            and D._slag_state() == snap_slag_state and _d_slag() == _d_slag_before,
            f"health {_d_col(_d_table(obj), 'EnemyHealthMultiplier')} vs "
            f"{_d_col(snap_table, 'EnemyHealthMultiplier')}, healing {_d_heal(obj)} vs {snap_heal}, "
            f"DoT {_d_dot(obj)} vs {snap_dot}, slag {D._slag_state()} vs {snap_slag_state}",
        )


_d_slag_before = _d_slag()
try:
    _d_main()
finally:
    # Even if something raises on the way through, the tally still prints and the bridge
    # reports the traceback under it.
    summary()
