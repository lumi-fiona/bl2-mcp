# The pause-menu sliders - checks for the claims in features/menusliders.py.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/menusliders.py
#
# Nothing here waits for anything, so it is one request. The one claim this CANNOT settle is the
# one that matters most to a person: whether the game's own settings screen actually draws the
# wider range and lets the mouse be set to it. That needs somebody to open the pause menu and
# drag the slider, and it lives in menusliders-needs-travel.py.
#
# Run it with a character loaded or at the main menu - either works, the profile object exists
# in both. Every number this moves is put back in the finally.

from bl2_modern.features import menusliders as m

reset()

prof, how = m._profile_settings()
print(f"profile object: {prof} (via {how})")


def mappings():
    return None if prof is None else prof.ProfileMappings


def entry(name):
    """(index, MinVal, MaxVal, RangeIncrement) for one setting, or None if it is not there."""
    table = mappings()
    if table is None:
        return None
    for i in range(len(table)):
        try:
            item = table[i]
            if str(item.Name) != name:
                continue
            increment = None
            try:
                increment = float(item.RangeIncrement)
            except Exception:
                pass
            return i, float(item.MinVal), float(item.MaxVal), increment
        except Exception:
            continue
    return None


WANTED = [name for name, _id, _floor, _ceiling in m.TARGETS]

before_options = [
    (o, o.value)
    for o in (m.enabled, m.mouse_floor, m.mouse_ceiling, m.pad_ceiling, m.bright_ceiling)
]
before_entries = {name: entry(name) for name in WANTED}
print(f"before: {before_entries}")

try:
    check(
        "the game hands over a profile object to read the slider limits off",
        prof is not None,
        f"found via {how}",
    )

    table = mappings()
    check(
        "that profile carries a table of slider limits",
        table is not None and len(table) > 0,
        f"{0 if table is None else len(table)} entries",
    )

    # THE LOAD-BEARING CLAIM. Everything in the feature file rests on the entries being findable
    # by the name the backlog recorded. If this fails, the names are wrong and the feature is
    # matching nothing - which would otherwise look exactly like a feature with nothing to do.
    missing = [name for name in WANTED if before_entries[name] is None]
    check(
        "every slider this pack widens is in the table under the name it was looked up by",
        not missing,
        f"not found by name: {missing}; found: "
        f"{[n for n in WANTED if before_entries[n] is not None]}",
    )

    check(
        "each of those entries really does carry a lowest and a highest value",
        all(before_entries[n] is not None for n in WANTED),
        f"{ {n: before_entries[n] for n in WANTED} }",
    )

    check(
        "the pack recorded what the game's own limits were before it widened anything",
        set(m._stock) >= {n for n in WANTED if before_entries[n] is not None},
        f"recorded: {m._stock}",
    )

    # Field of view is display.py's, and two owners for one number is how a player ends up
    # thinking the menu is broken.
    check(
        "field of view is deliberately not one of the sliders this widens",
        not any("FOV" in name.upper() or "FIELDOFVIEW" in name.upper() for name in WANTED),
        f"widens: {WANTED}",
    )

    # --- widening actually lands -----------------------------------------------------------

    mouse = "MouseSensitivity"
    if before_entries[mouse] is None:
        check("asking for a faster mouse than the game allows widens the menu's own limit",
              False, "MouseSensitivity is not in the table, so nothing could be tried")
        check("the game's own step size survives being widened", False, "same reason")
    else:
        m.enabled.value = True
        m.mouse_ceiling.value = 1500
        m.mouse_floor.value = 1
        after = entry(mouse)
        check(
            "asking for a faster mouse than the game allows widens the menu's own limit",
            after is not None and abs(after[2] - 1500.0) < 1e-4 and abs(after[1] - 1.0) < 1e-4,
            f"MouseSensitivity now runs {after[1]} to {after[2]} (was "
            f"{before_entries[mouse][1]} to {before_entries[mouse][2]})",
        )
        # The BLCM mod writes the whole struct in one command, which blanks every field it does
        # not mention - RangeIncrement included. This one edits two fields, so the step survives.
        check(
            "the game's own step size survives being widened",
            after is not None and after[3] == before_entries[mouse][3],
            f"RangeIncrement {before_entries[mouse][3]} -> {after[3]}",
        )

        # --- 0 means leave it alone -----------------------------------------------------------
        m.mouse_ceiling.value = 0
        after_zero = entry(mouse)
        check(
            "setting the highest number to 0 hands the game's own limit back",
            after_zero is not None
            and abs(after_zero[2] - m._stock[mouse][1]) < 1e-4,
            f"highest is {after_zero[2]}, the game's own was {m._stock[mouse][1]}",
        )

        # --- switching the feature off puts everything back ------------------------------------
        m.mouse_ceiling.value = 1500
        m.enabled.value = False
        off = entry(mouse)
        check(
            "turning the whole feature off puts the game's own limits back",
            off is not None
            and abs(off[1] - m._stock[mouse][0]) < 1e-4
            and abs(off[2] - m._stock[mouse][1]) < 1e-4,
            f"{off[1]} to {off[2]} with the feature off; the game's own were {m._stock[mouse]}",
        )

    # --- a profile that is not one ------------------------------------------------------------
    # _apply must survive being handed nothing rather than taking the pack down with it.
    hurt = "nothing"
    real = m._profile_settings
    try:
        m._profile_settings = lambda: (None, "there is no profile in this test")
        m._apply()
    except Exception as ex:
        hurt = repr(ex)
    finally:
        m._profile_settings = real
    check(
        "the feature survives there being no profile to widen",
        hurt == "nothing",
        f"with no profile object it raised {hurt}",
    )

finally:
    for option, old in before_options:
        if hasattr(option, "_on_change_recursion_guard"):
            del option._on_change_recursion_guard
    for option, old in before_options:
        option.value = old
    m._apply()

    now = {name: entry(name) for name in WANTED}
    same = all(
        before_entries[n] is None or (now[n] is not None and now[n] == before_entries[n])
        for n in WANTED
    )
    check(
        "every limit this test moved is back where it started",
        same and [o.value for o, _ in before_options] == [v for _, v in before_options],
        f"now {now} vs before {before_entries}; "
        f"options {[o.value for o, _ in before_options]}",
    )

summary()
