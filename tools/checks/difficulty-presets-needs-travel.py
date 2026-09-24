# Difficulty presets, the half that needs a map to load - AUDIT-RAW/difficulty-presets.md
#
# The same file is sent twice. It knows which run it is on by whether it left state behind
# in the bridge's scope (bridge.py:68 keeps that scope between requests), so there is no
# waiting, polling or sleeping inside the game - the waiting is the operator's, outside.
#
# RUN IT LIKE THIS, from the game folder:
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/difficulty-presets-needs-travel.py
#        - snapshots everything, sets the preset to UVHM, deliberately wrecks the health
#          multiplier on the live table, then fast-travels. It REFUSES to do any of that
#          unless the character is already in playthrough 2, because arming it on a
#          playthrough-0 character would convert them and swap their mission list.
#        - it also moves the character to another map. Travel back afterwards.
#
#   2. wait for the load, watching from outside:
#        echo 'print(where())' | bash bl2-mcp/tools/ask.sh
#      repeat until the map name changes (30-90 seconds).
#
#   3. ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/difficulty-presets-needs-travel.py
#        - measures what the level load did and puts everything back.
#
# To aim step 1 somewhere in particular (a map with enemies in it makes the last check
# worth something), name the station first:
#   echo 'DIFF_TRAVEL_TARGET = "Sanctuary"' | bash bl2-mcp/tools/ask.sh
#
# THE THROWAWAY-CHARACTER CHECK (claim 5) is a third, separate thing. It converts the live
# character to Ultimate Vault Hunter Mode permanently - nothing in the feature ever switches
# back - and switching playthrough swaps the character's whole mission list
# (BL2-UVHM-DESIGN.md:186). So it only runs when you say out loud that this character is
# expendable:
#   echo 'DIFF_THROWAWAY_CHARACTER = True' | bash bl2-mcp/tools/ask.sh
#   bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/difficulty-presets-needs-travel.py
# Make a brand-new character for it. Do not point it at a save you like.
#
# Claim 6 (does the playthrough survive a save/quit/reload) is NOT covered here. It needs
# Enter pressed at the character-select menu, which steals the screen, and the answer only
# means anything on a character you have just converted - so run it by hand after the
# throwaway check above: note GetCurrentPlaythrough(), quit to the menu, reload, read it
# again.

reset()

import unrealsdk
from bl2_modern.difficulty import SETTABLE
from bl2_modern.features import difficulty as D


def _dt_table(obj):
    return [{f: getattr(t, f) for f in SETTABLE} for t in obj.BalanceModifiers]


def _dt_heal(obj):
    out = []
    for tier in obj.BalanceModifiers:
        for effect in tier.AttributeEffectsForSpawnedEnemies:
            if D.HEALING_ATTR in str(effect.AttributeToModify):
                out.append(effect.BaseModifierValue.BaseValueScaleConstant)
    return out


def _dt_put_table(obj, rows):
    for tier, row in zip(obj.BalanceModifiers, rows):
        for name, value in row.items():
            setattr(tier, name, value)


def _dt_put_heal(obj, values):
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


def _dt_object():
    return unrealsdk.find_object("BalanceModifierDefinition", D.TARGET)


def _dt_pawn_level(pawn):
    """Whichever accessor this build has, or None if it has neither."""
    for attempt in ("GetExpLevel", "GetGameStage"):
        try:
            return int(getattr(pawn, attempt)())
        except Exception:  # noqa: BLE001, PERF203 - trying which one exists
            continue
    return None


def _dt_arm():
    """Run one: wreck the table on purpose, then leave the map."""
    controller = pc()
    if controller is None:
        print("no player controller - load a character first")
        return

    playthrough = controller.GetCurrentPlaythrough()
    if playthrough != D.UVHM_PLAYTHROUGH:
        print(
            f"REFUSED: this character is in playthrough {playthrough}, not "
            f"{D.UVHM_PLAYTHROUGH}. Arming would set the preset to UVHM, and the spawn hook "
            f"would then convert them on the next level load - swapping the mission list of a "
            f"character you may care about. Run this on a character already in UVHM.",
        )
        return

    obj = _dt_object()
    state = {
        "map": where(),
        "table": _dt_table(obj),
        "heal": _dt_heal(obj),
        "memory": dict(D._healing_original),
        "answer_at_creation": D._answer_at_creation,
        "options": [(o, o.value) for o in (D.preset, D.start_level, D.custom_health)],
        "playthrough": playthrough,
    }

    D.start_level.value = 1
    D.preset.value = "UVHM"
    D._apply("UVHM")

    # Wreck it by hand, underneath the feature, so that finding 4.0 afterwards can only mean
    # the spawn hook re-applied the preset on the level load.
    for tier in obj.BalanceModifiers:
        tier.EnemyHealthMultiplier = 1.0
    state["wrecked"] = [round(t.EnemyHealthMultiplier, 3) for t in obj.BalanceModifiers]
    if not all(abs(v - 1.0) < 1e-3 for v in state["wrecked"]):
        # If the write did not land, run two would find 4.0 and call it a re-apply when
        # nothing had ever been undone - a check that passes by not being able to fail.
        print(
            f"REFUSED: the health multipliers read {state['wrecked']} after being set to 1.0, "
            f"so this write did not land and run two could not tell a re-apply from a no-op. "
            f"Run difficulty-presets.py first - its first check is exactly this.",
        )
        for option, value in state["options"]:
            option.value = value
        _dt_put_table(obj, state["table"])
        return

    target = globals().get("DIFF_TRAVEL_TARGET")
    if not target:
        here = state["map"].lower()
        elsewhere = [
            name
            for name in sorted(stations())
            if name.lower() not in here and here.split("_")[0] not in name.lower()
        ]
        target = "Sanctuary" if "Sanctuary" in elsewhere else (elsewhere[0] if elsewhere else None)
    if target is None:
        print("no station to travel to that is not this map - set DIFF_TRAVEL_TARGET yourself")
        for option, value in state["options"]:
            option.value = value
        _dt_put_table(obj, state["table"])
        return

    # The state global goes in only once the travel is actually under way. Setting it first
    # and then failing to travel would leave the next run measuring a wrecked table it can
    # no longer explain, with nothing putting it back.
    try:
        travel_to(target)
    except Exception as ex:  # noqa: BLE001
        print(f"could not travel to {target!r}: {ex!r} - putting everything back")
        # Options first, table last: putting the preset back fires its on_change, which
        # writes the table again.
        for option, value in state["options"]:
            option.value = value
        _dt_put_table(obj, state["table"])
        return

    globals()["DIFF_TRAVEL"] = state
    print(
        f"armed in {state['map']}: preset UVHM, health multipliers forced to "
        f"{state['wrecked']}, travelling to {target!r}. "
        f"Watch `print(where())` until the map changes, then send this file again.",
    )


def _dt_measure(state):
    """Run two: what the level load did, then put everything back."""
    obj = _dt_object()
    now = where()
    if now == state["map"]:
        print(
            f"still in {now} - the travel has not landed yet. Wait and send this file again; "
            f"nothing has been measured and nothing has been put back.",
        )
        return

    controller = pc()
    try:
        rows = _dt_table(obj)
        health = [round(float(r["EnemyHealthMultiplier"]), 3) for r in rows]
        check(
            "loading another map puts the chosen preset back onto the tuning table",
            all(abs(float(r["EnemyHealthMultiplier"]) - 4.0) < 1e-3 for r in rows),
            f"health {health} in {now}, left at {state['wrecked']} in {state['map']} - "
            f"levels now {[int(r['MinEffectiveLevel']) for r in rows]}",
        )
        playthrough = controller.GetCurrentPlaythrough()
        check(
            "the character is still in Ultimate Vault Hunter Mode after a map change",
            playthrough == D.UVHM_PLAYTHROUGH,
            f"playthrough {playthrough} in {now}, was {state['playthrough']} in {state['map']}",
        )

        # Claim 11, the headline promise. It is only worth reading in a map with real
        # enemies in it - a town full of civilians will show fixed-level NPCs and this will
        # say so rather than quietly passing. Aim run one somewhere with a fight in it.
        pawns = [p for p in find_actor("WillowAIPawn") if getattr(p, "Health", 0) > 0]
        if len(pawns) < 3:
            print(f"skipped the enemy-level check: only {len(pawns)} live AI pawns in {now}")
        else:
            mine = level(controller)
            seen = [(str(p.Name)[:40], _dt_pawn_level(p)) for p in pawns[:40]]
            unreadable = [n for n, lvl in seen if lvl is None]
            off = [(n, lvl) for n, lvl in seen if lvl is not None and abs(lvl - mine) > 2]
            check(
                "the things in this map are at the player's own level",
                not unreadable and not off,
                f"player {mine}, {len(pawns)} pawns; "
                + (f"no level accessor on {len(unreadable)} of them; " if unreadable else "")
                + f"off by more than 2: {off[:8]}",
            )
    finally:
        D._healing_original.clear()
        D._healing_original.update(state["memory"])
        D._answer_at_creation = state["answer_at_creation"]
        for option, value in state["options"]:
            try:
                option.value = value
            except Exception as ex:  # noqa: BLE001
                print(f"could not put {option.identifier} back: {ex!r}")
        try:
            _dt_put_heal(obj, state["heal"])
            _dt_put_table(obj, state["table"])
        except Exception as ex:  # noqa: BLE001
            print(f"could not put the tuning table back: {ex!r}")
        globals().pop("DIFF_TRAVEL", None)
        check(
            "everything this file changed was put back the way it was found",
            _dt_table(obj) == state["table"] and _dt_heal(obj) == state["heal"],
            f"preset back to {D.preset.value!r}; note the character is now in {now}, not "
            f"{state['map']} - travel back yourself",
        )


def _dt_throwaway():
    """The one check that only means anything on a character nobody wants."""
    controller = pc()
    before = controller.GetCurrentPlaythrough()
    if before == D.UVHM_PLAYTHROUGH:
        print(
            "this character is already in UVHM, so _switch_to_uvhm would return True at its "
            "first branch (difficulty.py:293) without proving anything. Make a NEW character "
            "and run this again - playthrough 0 is the only case that matters.",
        )
        return
    moved = D._switch_to_uvhm(controller)
    after = controller.GetCurrentPlaythrough()
    check(
        "switching a first-playthrough character puts them into Ultimate Vault Hunter Mode",
        moved is True and after == D.UVHM_PLAYTHROUGH,
        f"playthrough {before} -> {after}, the function returned {moved}",
    )
    print(
        "NOT undone: nothing in the feature ever calls SetCurrentPlaythrough back down, "
        "which is claim 6's other half. This character is in UVHM for good.",
    )


if globals().get("DIFF_THROWAWAY_CHARACTER") is True:
    _dt_throwaway()
elif "DIFF_TRAVEL" in globals():
    _dt_measure(globals()["DIFF_TRAVEL"])
else:
    _dt_arm()
summary()
