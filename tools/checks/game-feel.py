# Game feel + the ini editor - checks for the claims in AUDIT-RAW/game-feel-configtweaks.md
# and AUDIT-RAW/game-files-ini-editor.md that can only be answered from inside the game.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/game-feel-and-files.py
#
# NOTHING HERE WRITES AN INI. The one test that runs configtweaks._apply() for real replaces
# configtweaks.edit_ini with a spy first, so the writer is never reached and the owner's
# config files are only ever opened for reading. The ini files themselves are checked from
# game-feel-and-files-files.py, which runs as ordinary Python.
reset()

import unrealsdk
from bl2_modern import gamefiles as gf
from bl2_modern.features import configtweaks as ct


def _peek(get):
    """Read something that may not be there, without killing the rest of the file."""
    try:
        return True, get()
    except Exception as ex:  # noqa: BLE001 - the point is to survive whatever it is
        return False, repr(ex)


def _ini_value(path, section, key):
    """
    The value of one key inside one named section, or None.

    Section-aware on purpose: WillowEngine.ini holds PoolSize twice - once under
    [TextureStreaming] which the pack edits and once under [Wwise.ComponentPool] which it
    must not - so a bare key match would read the wrong one.
    """
    want_section, want_key = section.lower(), key.lower()
    current = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped.lower()
        elif current == want_section and "=" in stripped:
            name, value = stripped.split("=", 1)
            if name.strip().lower() == want_key:
                return value.strip()
    return None


p = pc()
CONFIG = gf.config_dir()
ENGINE_INI = CONFIG / "WillowEngine.ini"

_REAL_GET_PC = ct.get_pc
_REAL_EDIT_INI = ct.edit_ini
SAVED = [(option, option.value) for option, *_ in ct.TWEAKS + ct.NUMBERS]
seen = []  # what the edit_ini spy was asked to write


def _spy(filename, section, changes):
    seen.append((filename, section, dict(changes)))
    return {}


def _no_player(*_a, **_kw):
    # What mods_base's willow get_pc really does on an empty GamePlayers: it indexes [0]
    # (mods_base/__init__.py:160-161) and IndexError comes out, rather than None.
    raise IndexError("no local player")


class _DeadConsole:
    """A player controller whose console has stopped answering."""

    def ConsoleCommand(self, _command):  # noqa: N802 - this is the game's own spelling
        raise RuntimeError("pretend the console is gone")


try:
    # --- what the running session actually holds ------------------------------------------
    # Audit claim 3: "Both booleans take effect immediately, in the running session."

    ok, shake = _peek(lambda: p.bLandingShake)
    check(
        "landing camera shake is off on the player controller that is playing right now",
        ok and shake in (False, 0),
        f"pc.bLandingShake = {shake!r}",
    )

    ok, smoothing = _peek(lambda: p.PlayerInput.bEnableMouseSmoothing)
    # The class matters: the ini section and the console set both name Engine.PlayerInput, but
    # the object the game really reads the mouse through is a WillowPlayerInput subclass of it.
    _, input_class = _peek(lambda: str(p.PlayerInput.Class.Name))
    check(
        "mouse smoothing is off on the player input object the game is reading the mouse through",
        ok and smoothing in (False, 0),
        f"pc.PlayerInput.bEnableMouseSmoothing = {smoothing!r} on a {input_class}",
    )

    ok, cdo = _peek(
        lambda: unrealsdk.find_class("WillowPlayerController").ClassDefaultObject.bLandingShake,
    )
    check(
        "landing shake is off on the class defaults too, which is what every player controller "
        "spawned after this copies from",
        ok and cdo in (False, 0),
        f"WillowPlayerController default bLandingShake = {cdo!r}",
    )

    # --- what `live = True` is worth ------------------------------------------------------
    # Audit claim 4. configtweaks.py:131-132 sets live = True on the strength of
    # ConsoleCommand not raising, and the log at :146 then says "and is live now".

    raised = False
    try:
        p.ConsoleCommand("set Engine.PlayerInput bNoSuchPropertyAtAll True")
    except Exception as ex:  # noqa: BLE001
        raised = True
    check(
        "a console set for a property that does not exist comes back without complaining, so "
        "'and is live now' in the log is not a measurement of anything",
        not raised,
        "set Engine.PlayerInput bNoSuchPropertyAtAll True returned quietly"
        if not raised
        else "it raised, so ConsoleCommand does report bad sets after all",
    )

    # The read-back the log should have been doing. This is also the only honest way to settle
    # what `set` reaches: the audit asserts it only touches the class default object, UE3's
    # GlobalSetProperty is documented as walking every instance of the class. Measure it.
    # Landing shake is on for the few microseconds between here and the finally below - the
    # one visible change this file makes, and the finally puts it back and then checks it.
    _peek(lambda: p.ConsoleCommand("set WillowGame.WillowPlayerController bLandingShake True"))
    ok, after = _peek(lambda: p.bLandingShake)
    check(
        "a console set reaches the player controller that already exists, not only the class "
        "defaults - which is what makes 'takes effect immediately' possible at all",
        ok and after in (True, 1),
        f"after `set ... bLandingShake True`, pc.bLandingShake = {after!r}",
    )

    # --- the guarantee the comment at configtweaks.py:133 was written to protect -----------
    # Audit claim 13. `pc = get_pc()` sits at :119, outside every try, and the first try does
    # not start until :130.

    ct.edit_ini = _spy
    ct.get_pc = _no_player
    seen.clear()
    blew_up = None
    try:
        ct._apply()
    except Exception as ex:  # noqa: BLE001
        blew_up = repr(ex)
    check(
        "the ini half of the game-feel tweaks is still done when there is no player controller "
        "to talk to",
        blew_up is None and len(seen) == 2,
        f"edit_ini asked for {len(seen)} writes; _apply() raised {blew_up}",
    )

    # The same guarantee, for the failure the comment was actually thinking of.
    ct.get_pc = lambda *_a, **_kw: _DeadConsole()
    seen.clear()
    blew_up = None
    try:
        ct._apply()
    except Exception as ex:  # noqa: BLE001
        blew_up = repr(ex)
    check(
        "the ini half is still done when the console command itself fails",
        blew_up is None and len(seen) == 2,
        f"edit_ini asked for {[(name, changes) for name, _section, changes in seen]}; "
        f"_apply() raised {blew_up}",
    )

    ct.get_pc = _REAL_GET_PC
    ct.edit_ini = _REAL_EDIT_INI

    # --- what happens when a player toggles one of these in the menu ----------------------
    # Audit claim 11, and the "Takes effect immediately." in the descriptions at :41 and :55.

    silent = [
        option.identifier
        for option, *_ in ct.TWEAKS + ct.NUMBERS
        if option.on_change_anytime is None and option.on_change_while_enabled is None
    ]
    # INVERTED 2026-08-20. This used to assert that NONE of them had a callback, which was true
    # and was the bug: flipping "Turn off mouse smoothing" in the menu changed the switch and
    # nothing else until the next character load. They all carry one now.
    check(
        "every game-feel switch takes effect when you flip it, rather than at the next reload",
        not silent,
        f"{len(silent)} switches still run nothing when flipped: {silent}",
    )

    # Watching one key rather than the whole file on purpose: the game rewrites its own ini
    # files while it runs, so "the bytes changed" would pass on somebody else's write.
    physx, physx_file, physx_section, physx_key, _on, _off = ct.NUMBERS[0]
    physx_path = CONFIG / physx_file
    was = _ini_value(physx_path, physx_section, physx_key)
    physx.value = not physx.value
    now = _ini_value(physx_path, physx_section, physx_key)
    check(
        "toggling a game-feel switch in the mod menu writes the new value into the ini",
        now != was,
        f"flipped '{physx.identifier}' to {physx.value!r}; {physx_key} in {physx_file} went "
        f"{was!r} -> {now!r}",
    )
    physx.value = not physx.value

    # --- the texture buffer, where a corrected default did not take ----------------------
    # Audit claim 10. default_value is captured in ValueOption.__post_init__ at import, i.e.
    # the value the source ships; .value is what the saved settings file put there afterwards.

    pool = ct.NUMBERS[1][0]
    check(
        "the texture buffer switch ships defaulted to OFF, as configtweaks.py:90-97 says it was "
        "corrected to be",
        pool.default_value is False,
        f"shipped default = {pool.default_value!r}",
    )
    check(
        "the texture buffer switch is actually OFF this session, so the owner's own pool size stays",
        pool.value is False,
        f"value = {pool.value!r} against a shipped default of {pool.default_value!r} - a saved "
        f"settings file overrides a changed default, it does not migrate to it",
    )

    # --- the switches against the files they are supposed to have written ----------------
    # This is the end-to-end one: if a toggle ever happened without an apply behind it, or a
    # section name went stale, the file stops agreeing with the switch and this fails.

    for option, filename, section, key, _owner in ct.TWEAKS:
        wanted = "False" if option.value else "True"
        got = _ini_value(CONFIG / filename, section, key)
        check(
            f"{key} in {filename} says what the '{option.identifier}' switch says",
            got == wanted,
            f"{section} {key}={got!r}, switch wants {wanted!r}",
        )

    for option, filename, section, key, on_value, off_value in ct.NUMBERS:
        wanted = on_value if option.value else off_value
        got = _ini_value(CONFIG / filename, section, key)
        check(
            f"{key} in {filename} says what the '{option.identifier}' switch says",
            got == wanted,
            f"{section} {key}={got!r}, switch wants {wanted!r}",
        )

finally:
    # Everything this file touched, put back. The console flag first, because leaving landing
    # shake ON is the one change here a player would feel.
    _peek(lambda: p.ConsoleCommand("set WillowGame.WillowPlayerController bLandingShake False"))
    ok, back = _peek(lambda: p.bLandingShake)
    if not ok or back not in (False, 0):
        _peek(lambda: setattr(p, "bLandingShake", False))
        ok, back = _peek(lambda: p.bLandingShake)

    ct.get_pc = _REAL_GET_PC
    ct.edit_ini = _REAL_EDIT_INI
    for option, value in SAVED:
        option.value = value

    check(
        "landing camera shake is off again now this file has finished poking at it",
        ok and back in (False, 0),
        f"pc.bLandingShake = {back!r}",
    )
    check(
        "configtweaks has its real get_pc and edit_ini back, so the next apply writes files again",
        ct.get_pc is _REAL_GET_PC and ct.edit_ini is _REAL_EDIT_INI,
        f"get_pc={ct.get_pc!r}",
    )
    check(
        "every game-feel switch is back at the value it had before this file ran",
        all(option.value == value for option, value in SAVED),
        f"{[(o.identifier, o.value) for o, _v in SAVED]}",
    )

summary()
