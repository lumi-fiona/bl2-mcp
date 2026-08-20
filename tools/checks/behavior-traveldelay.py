# Multiplayer fast-travel delay - behavior checks for features/traveldelay.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-traveldelay.py
#
# MOST OF THIS TOUCHES NOTHING REAL. The gating and number checks run against a spy standing in
# for get_pc(), which only ever records the console-command string it was handed.
#
# ONE SECTION IS REAL, and deliberately so: a spy can only prove what was typed, never that the
# game took it. Near the end this reads GD_Globals.General.Globals.TravelDelay, moves the slider
# one second, reads it again, and puts it straight back - the same write any ordinary slider move
# already does, on a value that only affects how long a fast-travel wait screen lasts.
reset()

from bl2_modern import core
from bl2_modern.features import traveldelay as TD

p = pc()


class SpyConsole:
    """Stands in for get_pc(), recording every console command handed to it."""

    def __init__(self):
        self.sent = []
        self.WorldInfo = self  # unused here, but _apply() only ever calls ConsoleCommand

    def ConsoleCommand(self, command):
        self.sent.append(command)


class AngryConsole:
    def ConsoleCommand(self, _command):
        raise RuntimeError("pretend the console is gone")


def _no_player():
    raise IndexError("no local player")


real_get_pc = TD.get_pc
real_is_client = TD._is_client
real_current_delay = TD._current_delay
was_value = TD.value.value
was_touched = TD._touched

try:
    # --- the feature is wired into the core as a live, restart-free write ------------------

    feature = next(
        (f for f in core.all_features() if f.name == "Multiplayer fast-travel delay"), None,
    )
    check(
        "the travel delay feature loaded",
        feature is not None and feature.failed is None,
        feature.failed if feature else "no feature by that name",
    )
    if feature is not None:
        check(
            "the core can re-run it when it re-applies game data - the same thing BL2Fix's "
            "own Enable() does once, at process start",
            feature.apply is not None,
            "apply is None: nothing would ever run this at the main menu",
        )
        check(
            "it is marked as writing game data, so the main-menu pass includes it",
            feature.writes_game_data,
            f"writes_game_data={getattr(feature, 'writes_game_data', None)}",
        )
        check(
            "the slider is carried to the menu",
            TD.value in feature.options,
            f"feature.options has {len(feature.options)} entries",
        )
    check(
        "the on_change callback is installed as on_change_anytime, the one that actually fires",
        TD.value.on_change_anytime is TD._on_change,
        f"on_change_anytime={TD.value.on_change_anytime!r}",
    )

    # --- _is_client() agrees with reading NetMode directly, whatever state this session is
    # actually in - this does not assume single-player, it just checks the function is honest
    # about whatever the real NetMode says right now -----------------------------------------

    try:
        real_netmode = int(p.WorldInfo.NetMode)
        netmode_ok = True
    except Exception as ex:
        real_netmode = None
        netmode_ok = False
    if netmode_ok:
        check(
            "_is_client() agrees with reading WorldInfo.NetMode directly",
            TD._is_client() == (real_netmode == 3),
            f"NetMode={real_netmode}, _is_client()={TD._is_client()}",
        )
    else:
        print("[SKIP] WorldInfo.NetMode could be read directly to cross-check _is_client()")

    # --- what the slider says is what the game is told, and the client gate ------------------
    # Against a spy, so nothing real is written here. The game's own delay is stubbed to a number
    # no slider position can ask for, so every apply below really does send something - otherwise
    # the "it already reads that, send nothing" shortcut would swallow the ones that matched.
    #
    # NOTE ON COUNTING: assigning to option.value fires the change callback, which applies. So an
    # assignment sends one command all by itself, and an explicit _apply() after it sends a
    # second. Each block below clears the spy first and asserts exactly what that block caused.

    spy = SpyConsole()
    TD.get_pc = lambda: spy
    TD._current_delay = lambda: 99.0

    TD._is_client = lambda: True
    spy.sent.clear()
    TD.value.value = 5
    TD._apply()
    check(
        "a guest's copy of this switch sends nothing at all, neither on the slider moving nor "
        "on a main-menu apply",
        spy.sent == [],
        f"sent {spy.sent}",
    )

    TD._is_client = lambda: False
    spy.sent.clear()
    TD.value.value = 1
    check(
        "moving the slider to its lowest sends exactly that number, with no offset of any kind",
        spy.sent == ["set globals traveldelay 1"],
        f"sent {spy.sent}",
    )

    spy.sent.clear()
    TD.value.value = 11
    TD._apply()
    check(
        "and at its highest - once for the slider moving, once for the explicit apply, both the "
        "number on the slider",
        spy.sent == ["set globals traveldelay 11", "set globals traveldelay 11"],
        f"sent {spy.sent}",
    )

    check(
        "the slider's own default is the number the game already uses, so an untouched slider "
        "asks for no change at all",
        TD.value.default_value == TD.VANILLA_SECONDS == 3,
        f"default={TD.value.default_value!r}, VANILLA_SECONDS={TD.VANILLA_SECONDS!r}",
    )
    check(
        "the slider cannot ask for a number BL2Fix could never send, and cannot ask for 0, "
        "which nobody has tested",
        (TD.value.min_value, TD.value.max_value) == (1, 11),
        f"range {TD.value.min_value}-{TD.value.max_value}",
    )

    # The shortcut itself: when the game already holds the wanted number, nothing is sent.
    TD._current_delay = lambda: 7.0
    spy.sent.clear()
    TD.value.value = 7
    TD._apply()
    check(
        "asking for the number the game already holds sends nothing",
        spy.sent == [],
        f"sent {spy.sent}",
    )
    TD._current_delay = lambda: 99.0

    # A console command that raises must not escape _apply().
    TD.get_pc = lambda: AngryConsole()
    blew_up = None
    try:
        TD._apply()
    except Exception as ex:
        blew_up = repr(ex)
    check(
        "a console command that raises is contained rather than taking the pack down",
        blew_up is None,
        f"_apply() raised {blew_up}",
    )

    # No player controller at all must not escape either - configtweaks.py's own get_pc()
    # comment applies here too: it raises, it does not return None.
    TD.get_pc = _no_player
    blew_up = None
    try:
        TD._apply()
    except Exception as ex:
        blew_up = repr(ex)
    check(
        "no player controller yet is handled the same way, not thrown into the caller",
        blew_up is None,
        f"_apply() raised {blew_up}",
    )

    # --- moving the slider in the menu applies immediately, not just at the next launch -----

    TD.get_pc = lambda: spy
    spy.sent.clear()
    TD.value.value = 6
    check(
        "changing the slider writes a new console command immediately, without a restart",
        spy.sent == ["set globals traveldelay 6"],
        f"sent {spy.sent}",
    )

    # --- THE REAL THING: read the game's own TravelDelay, move the slider, read it again ----
    # Everything above ran against a spy and proves only what was typed. This section writes for
    # real and reads the property back, which is the only way to know the command lands at all.

    TD.value.value = was_value
    TD.get_pc = real_get_pc
    TD._is_client = real_is_client
    TD._current_delay = real_current_delay

    before = TD._current_delay()
    print(f"[PROBE] {TD.GLOBALS_PATH}.TravelDelay before anything real is written: {before!r}")
    if before is None:
        print(
            f"[SKIP] the real read/write pair   {TD.GLOBALS_PATH} could not be read here, so "
            f"there is nothing to compare a write against",
        )
    elif TD._is_client():
        print(
            "[SKIP] the real read/write pair   this machine is currently a guest, and the "
            "feature correctly refuses to send anything from here - see the module docstring",
        )
    else:
        check(
            "the game's own travel delay reads the vanilla 3 before anything is written - if it "
            "does not, something else in this session already moved it",
            abs(before - 3.0) < 1e-6,
            f"TravelDelay = {before!r}, expected the vanilla 3",
        )
        target = 4 if abs(before - 4.0) > 1e-6 else 5
        TD.value.value = target  # fires the change callback, which really applies
        after = TD._current_delay()
        check(
            "moving the slider really does move the game's own TravelDelay, to exactly the "
            "number on the slider - no offset between what is asked for and what lands",
            after is not None and abs(after - target) < 1e-6,
            f"slider={target}, TravelDelay before={before!r}, after={after!r}",
        )

        if 1 <= int(before) <= 11:
            TD.value.value = int(before)
        else:
            real_get_pc().ConsoleCommand(f"set globals traveldelay {before:g}")
        back = TD._current_delay()
        check(
            "and it is put straight back to what this file found on arrival",
            back is not None and abs(back - before) < 1e-6,
            f"TravelDelay = {back!r}, arrival was {before!r}",
        )

finally:
    TD.get_pc = real_get_pc
    TD._is_client = real_is_client
    TD._current_delay = real_current_delay
    TD.value.value = was_value
    TD._touched = was_touched
    check(
        "the slider is back where it started and the real get_pc/_is_client/_current_delay are "
        "restored",
        TD.value.value == was_value
        and TD.get_pc is real_get_pc
        and TD._is_client is real_is_client
        and TD._current_delay is real_current_delay,
        f"value={TD.value.value!r}",
    )

summary()
