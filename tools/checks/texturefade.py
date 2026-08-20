# Sharp textures - checks for the claims in features/texturefade.py.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/texturefade.py
#
# What this can and cannot settle. It can settle all the bookkeeping: that the pack notices the
# separate No Texture Fade mod, that it does not flip a second time on top of it, that the switch
# flips exactly once in each direction, and that a missing player controller is survived rather
# than thrown. It CANNOT settle whether textures actually stop fading - that is a picture on a
# screen and it lives in texturefade-needs-travel.py.
#
# Almost every check here runs with the command counted rather than run, so the picture does not
# change under whoever is looking at it. The two real calls at the end are deliberately a pair,
# so the game ends the way it started.
#
# Run it with a character loaded, or at least at the main menu. The feature deliberately decides
# nothing until there is a player controller, so with none the first two checks would report a
# feature that had not made its mind up rather than one that was wrong.

import sys

from bl2_modern.features import texturefade as t

reset()

was_option = t.enabled.value
was_state = t._fade_is_off
real_flip = t._flip
real_get_pc = t.get_pc

calls = []


def counted():
    calls.append(1)
    return True


try:
    check(
        "there is a player controller, without which this feature decides nothing on purpose",
        t._controller() is not None,
        f"controller is {t._controller()} - every check below reads as a failure without one",
    )

    # --- does it see the other mod ------------------------------------------------------------

    check(
        "the pack can tell whether the separate No Texture Fade mod is loaded",
        t._other_mod_ran() == (t.OTHER_MOD in sys.modules),
        f"{t.OTHER_MOD} in sys.modules: {t.OTHER_MOD in sys.modules}, "
        f"pack says {t._other_mod_ran()}",
    )
    print(
        f"NOTE: {t.OTHER_MOD} is "
        f"{'INSTALLED and has already flipped the fading once' if t._other_mod_ran() else 'not loaded'}",
    )

    # --- no double flip -----------------------------------------------------------------------
    # This is the whole reason the feature exists. With the other mod loaded the fading is
    # already off, so asking for it off again must do nothing at all. A flip here would turn
    # fading back ON while both menus still said it was off.

    t._flip = counted
    t._fade_is_off = None
    calls.clear()
    t.enabled.value = True
    t._apply()
    check(
        "asking for sharp textures when the other mod already did it flips nothing",
        (len(calls) == 0) if t._other_mod_ran() else (len(calls) == 1),
        f"{len(calls)} flips, with the other mod "
        f"{'loaded' if t._other_mod_ran() else 'absent'} - it should be "
        f"{0 if t._other_mod_ran() else 1}",
    )
    check(
        "having worked it out once, it believes the fading is off",
        t._fade_is_off is True,
        f"tracked state is {t._fade_is_off}",
    )

    calls.clear()
    t._apply()
    check(
        "running it again changes nothing, so nothing can drift by being applied twice",
        len(calls) == 0 and t._fade_is_off is True,
        f"{len(calls)} flips on the second run, state {t._fade_is_off}",
    )

    # --- the switch works in both directions ---------------------------------------------------

    calls.clear()
    t.enabled.value = False
    check(
        "turning the switch off flips the fading back on, exactly once",
        len(calls) == 1 and t._fade_is_off is False,
        f"{len(calls)} flips, state {t._fade_is_off}",
    )

    calls.clear()
    t.enabled.value = True
    check(
        "turning it back on flips again, exactly once",
        len(calls) == 1 and t._fade_is_off is True,
        f"{len(calls)} flips, state {t._fade_is_off}",
    )

    # --- the way out when the guess is wrong ----------------------------------------------------

    calls.clear()
    # `keybind` used as a decorator returns the bind object, not the function, and a bind is not
    # callable - the function is on .callback.
    t._flip_by_hand.callback()
    check(
        "the key flips it by hand and remembers that it did",
        len(calls) == 1 and t._fade_is_off is False,
        f"{len(calls)} flips, state {t._fade_is_off} - the point of this key is that the state "
        f"is a guess and this is the only way to correct it",
    )
    check(
        "that key ships unbound, so it cannot collide with anything already bound",
        t._flip_by_hand.key is None,
        f"default key is {t._flip_by_hand.key!r}",
    )

    # --- a flip with nobody to run it through -----------------------------------------------------

    t._flip = real_flip
    t.get_pc = lambda **kw: None
    hurt = "nothing"
    took = None
    try:
        took = t._flip()
    except Exception as ex:
        hurt = repr(ex)
    t.get_pc = real_get_pc
    check(
        "with no player controller the command is refused quietly rather than thrown",
        hurt == "nothing" and took is False,
        f"raised {hurt}, returned {took}",
    )

    # --- the game itself ---------------------------------------------------------------------
    # Two real calls, so the picture ends where it started. ConsoleCommand may well accept a
    # command the engine does not know and say nothing, so a pass here means "the call did not
    # blow up", NOT "the command exists". Only a pair of eyes settles the second one.

    first = t._flip()
    second = t._flip()
    check(
        "the game accepts the command itself, twice, without complaint",
        first and second,
        f"first call {first}, second call {second} - net zero flips, so nothing on screen "
        f"changed. This does not prove the engine knows the command.",
    )

finally:
    # The switch is put back with the command still COUNTED rather than run, because setting the
    # option fires its callback, and a real flip on the way out is exactly the thing this feature
    # exists to prevent. The two real calls above were a pair, so the game is already where it
    # started and only the bookkeeping needs restoring.
    t._flip = counted
    t.get_pc = real_get_pc
    if hasattr(t.enabled, "_on_change_recursion_guard"):
        del t.enabled._on_change_recursion_guard
    t._fade_is_off = was_state
    t.enabled.value = was_option
    t._fade_is_off = was_state
    t._flip = real_flip

    check(
        "the switch and the tracked state are back where they started",
        t.enabled.value == was_option and t._fade_is_off == was_state,
        f"switch {t.enabled.value} (was {was_option}), state {t._fade_is_off} (was {was_state})",
    )

summary()
