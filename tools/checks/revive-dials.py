# Going down and getting up - checks for features/revive.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/revive-dials.py
#
# The one thing this file CANNOT do is time a real revive: that needs a second player standing
# over a downed first one, and no amount of reading objects stands in for it. What it can do is
# prove the number the game will read is the number the option says, that the game's own number
# comes back when the feature is switched off, and that every failure path reports instead of
# pretending. Those are the parts that were unverified when this was written.
#
# Nothing here spawns, sells or destroys an item. It writes one float on one game-data object and
# puts it back in the finally block, whatever happens in between.
reset()

import unrealsdk

from bl2_modern import core
from bl2_modern.features import revive as R

# Everything this file is allowed to change, remembered before it changes any of it.
was_enabled = R.enabled.value
was_revive = R.revive_seconds.value
was_bleed = R.bleed_out_seconds.value
real_get_pc = R.get_pc

definition = None
touched = {}


def read(obj, name):
    try:
        return float(getattr(obj, name))
    except Exception as ex:
        return f"unreadable: {ex!r}"


try:
    # --- is the feature wired in at all --------------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Going down and getting up"), None)
    check(
        "the going-down feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "it ships switched off, because it changes how hard the game is",
        R.enabled.default_value is False,
        f"default is {R.enabled.default_value!r}",
    )
    check(
        "the core will re-apply it at the main menu, after the bundled patch has run",
        feature is not None and feature.writes_game_data and feature.apply is R._apply,
        f"writes_game_data={getattr(feature, 'writes_game_data', None)}, "
        f"apply={getattr(feature, 'apply', None)}",
    )
    check(
        "all three dials are carried to the mod menu",
        feature is not None
        and [o for o in feature.options]
        == [R.enabled, R.revive_seconds, R.bleed_out_seconds],
        [getattr(o, "identifier", o) for o in getattr(feature, "options", [])],
    )
    check(
        "the per-map arrival is carried too",
        feature is not None and feature.on_arrival is R.on_arrival,
        getattr(feature, "on_arrival", None),
    )
    check(
        "changing any of the three dials writes the new number straight away",
        all(
            option.on_change_anytime is R._changed
            for option in (R.enabled, R.revive_seconds, R.bleed_out_seconds)
        ),
        [option.on_change_anytime for option in (R.enabled, R.revive_seconds, R.bleed_out_seconds)],
    )

    # --- does the object the whole feature depends on exist ---------------------------------------
    # This is the claim nothing had ever run. It comes from another mod's source, not from this game.
    try:
        by_path = unrealsdk.find_object("InjuredDefinition", R.INJURED_PATH)
    except Exception as ex:
        by_path = None
    check(
        f"the game really has {R.INJURED_PATH}",
        by_path is not None,
        "if this fails the feature falls back to any loaded InjuredDefinition, which the next "
        "check covers",
    )

    definition = R._definition()
    check(
        "the feature finds an injured definition one way or the other",
        definition is not None,
        str(definition),
    )

    if definition is not None:
        for name in ("ReviveDuration",):
            touched[name] = read(definition, name)
        check(
            "ReviveDuration exists on it and reads as a number",
            isinstance(touched["ReviveDuration"], float),
            f"{R.INJURED_PATH}.ReviveDuration = {touched['ReviveDuration']!r}",
        )
        check(
            "and the game ships it at 5 seconds, which is what the mod this came from claims",
            touched.get("ReviveDuration") == 5.0,
            f"{touched.get('ReviveDuration')!r} - a different number is not a failure of the "
            f"feature, but it does mean the docstring is wrong",
        )

        # --- how long you stay down: the field nobody had a name for ------------------------------
        names = R._bleed_out_names(definition)
        found = names[0] if names else None
        check(
            "the names for how long you stay down really exist on the object",
            len(names) == len(R.BLEED_OUT_NAMES),
            f"tried {R.BLEED_OUT_NAMES}, found {names}. A failure here is the honest answer, "
            f"not a crash: the revive dial still works and the log says so",
        )
        check(
            "both of them are found - the solo number AND the one co-op uses",
            "BaseRejuvenateDelay" in names
            and "BaseMultiplePlayersRejuvenateDelay" in names,
            f"{names} - writing only one leaves the other case on the shipped number, and the "
            f"co-op one is the case this whole feature is for",
        )
        for name in names:
            touched[name] = read(definition, name)
            check(
                f"{name} reads as a number",
                isinstance(touched[name], float),
                f"{name} = {touched[name]!r}",
            )

        # --- the write itself ---------------------------------------------------------------------
        R.enabled.value = True
        R.revive_seconds.value = 2.5
        R._apply()
        check(
            "switching the feature on and asking for two and a half seconds puts two and a half "
            "seconds on the object the game reads",
            read(definition, "ReviveDuration") == 2.5,
            f"ReviveDuration = {read(definition, 'ReviveDuration')!r}",
        )

        R.revive_seconds.value = 0.0
        R._apply()
        check(
            "asking for an instant revive writes a zero rather than being treated as 'leave alone'",
            read(definition, "ReviveDuration") == 0.0,
            f"ReviveDuration = {read(definition, 'ReviveDuration')!r}",
        )

        R.enabled.value = False
        R._apply()
        check(
            "switching the feature off puts the game's own number back, not a number we typed",
            read(definition, "ReviveDuration") == touched["ReviveDuration"],
            f"ReviveDuration = {read(definition, 'ReviveDuration')!r}, the game shipped "
            f"{touched['ReviveDuration']!r}",
        )

        if found is not None:
            R.enabled.value = True
            R.bleed_out_seconds.value = 0
            R._apply()
            check(
                "leaving the bleed-out dial at zero leaves the game's own number completely alone, "
                "rather than making you die the instant you go down",
                read(definition, found) == touched[found],
                f"{found} = {read(definition, found)!r}, the game shipped {touched[found]!r}",
            )
            R.bleed_out_seconds.value = 20
            R._apply()
            check(
                "asking for twenty seconds on the floor writes twenty",
                read(definition, found) == 20.0,
                f"{found} = {read(definition, found)!r}",
            )
            R.enabled.value = False
            R._apply()
            check(
                "and switching off puts that one back too",
                read(definition, found) == touched[found],
                f"{found} = {read(definition, found)!r}",
            )

        # --- co-op: a machine that joined someone else's game must not write ----------------------
        class FakeClient:
            WorldInfo = type("W", (), {"NetMode": 3})()

        # Setting an option applies it immediately - that is the point of the on-change callback -
        # so the object is put back to the game's own number by hand first. Otherwise this would
        # be measuring the write the assignment did, not the one the client guard refused.
        R.enabled.value = True
        R.revive_seconds.value = 9.0
        setattr(definition, "ReviveDuration", touched["ReviveDuration"])
        R.get_pc = lambda *_a, **_k: FakeClient()
        R._apply()
        R.get_pc = real_get_pc
        check(
            "pretending to be a machine that joined someone else's game, nothing is written - the "
            "host owns the rules and two machines must not disagree about them",
            read(definition, "ReviveDuration") == touched["ReviveDuration"],
            f"ReviveDuration = {read(definition, 'ReviveDuration')!r} after applying as a client, "
            f"the game shipped {touched['ReviveDuration']!r}",
        )

        # --- nothing here may ever raise ------------------------------------------------------------
        escaped = None
        real_definition = R._definition
        try:
            R._definition = lambda: (_ for _ in ()).throw(RuntimeError("no such object"))
            R._apply()
        except Exception as ex:
            escaped = ex
        finally:
            R._definition = real_definition
        check(
            "a missing injured definition cannot throw out of the feature and into the game",
            escaped is None,
            f"{escaped!r}",
        )

        escaped = None
        try:
            R.get_pc = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no session"))
            R._apply()
        except Exception as ex:
            escaped = ex
        finally:
            R.get_pc = real_get_pc
        check(
            "neither can a session that does not exist yet",
            escaped is None,
            f"{escaped!r}",
        )

        # --- the keep-alive flag ---------------------------------------------------------------------
        flags = None
        try:
            flags = int(definition.ObjectFlags)
        except Exception as ex:
            flags = f"unreadable: {ex!r}"
        check(
            "the keep-alive flag really is set on the definition, so the collector leaves it alone",
            isinstance(flags, int) and bool(flags & R.KEEP_ALIVE_FLAG),
            f"ObjectFlags = {flags if not isinstance(flags, int) else hex(flags)}, looking for "
            f"{hex(R.KEEP_ALIVE_FLAG)}. This flag value came from the OLD SDK's KeepAlive and is "
            f"unverified here - a failure means the flag is wrong, not that the feature is broken",
        )

finally:
    R.get_pc = real_get_pc
    R.enabled.value = was_enabled
    R.revive_seconds.value = was_revive
    R.bleed_out_seconds.value = was_bleed
    try:
        R._apply()
    except Exception:
        pass
    if definition is not None:
        for name, original in touched.items():
            if isinstance(original, float):
                try:
                    setattr(definition, name, original)
                except Exception:
                    pass
    check(
        "every number this file changed is back where the game had it, and every option too",
        definition is None
        or (
            all(
                not isinstance(original, float) or read(definition, name) == original
                for name, original in touched.items()
            )
            and R.enabled.value == was_enabled
            and R.revive_seconds.value == was_revive
            and R.bleed_out_seconds.value == was_bleed
            and R.get_pc is real_get_pc
        ),
        f"{ {name: read(definition, name) for name in touched} if definition else 'no object'}, "
        f"wanted {touched}",
    )

summary()
