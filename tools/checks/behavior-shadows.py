# Dynamic shadows - behavior checks for features/shadows.py
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/behavior-shadows.py
#
# THE REAL FILE IS WRITTEN TO, TWICE, AND PUT BACK - the same shape coopfixes.py's own check
# uses for WillowGame.ini: edit_ini only ever touches the one key it is asked for and keeps the
# line count identical, so a flip-and-flip-back round trip against the real WillowEngine.ini is
# safe and is the only way to prove the key really exists and really moves. Nothing here can
# change what shadows look like THIS session either way - the feature itself says so, it only
# ever takes effect on the next launch.
reset()

from bl2_modern import core, gamefiles as gf
from bl2_modern.features import shadows as SH


def ini_value(path, section, key):
    """The value of one key inside one named section of a real ini file, or None."""
    want_section, want_key = section.lower(), key.lower()
    current = None
    for line in path.read_text(encoding="latin-1").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped.lower()
        elif current == want_section and "=" in stripped:
            name, _, value = stripped.partition("=")
            if name.strip().lower() == want_key:
                return value.strip()
    return None


CONFIG = gf.config_dir()
INI_PATH = CONFIG / SH.INI

real_edit_ini = SH.edit_ini
was = SH.enabled.value
# Read before the try, not inside it - the finally block needs this name to exist even if
# something below raises before this section's own check() call runs.
before = ini_value(INI_PATH, SH.SECTION, SH.KEY)

try:
    # --- the key this file depends on really exists, in the section claimed ----------------

    check(
        "DynamicShadows really exists in [SystemSettings] of the real WillowEngine.ini",
        before is not None,
        f"read back {before!r}",
    )
    light_before = ini_value(INI_PATH, SH.SECTION, "bAllowLightShafts")
    check(
        "bAllowLightShafts can be read too, so the 'untouched' check below is checking something "
        "real and not comparing None to None",
        light_before is not None,
        f"read back {light_before!r}",
    )

    # --- what _apply() actually asks edit_ini to write, spied rather than real -------------
    # This is the hard rule this whole file exists to defend: the changes dict must never grow
    # a second key, however the switch is set.

    seen = []

    def _spy(filename, section, changes):
        seen.append((filename, section, dict(changes)))
        return {}

    SH.edit_ini = _spy
    for state in (True, False, True):
        seen.clear()
        SH.enabled.value = state
        check(
            f"asking for the switch to be {state} writes exactly one key, DynamicShadows, and "
            f"nothing else",
            len(seen) == 1 and set(seen[0][2].keys()) == {"DynamicShadows"},
            f"edit_ini was asked to write {seen}",
        )
        check(
            f"and the value it asks for matches the switch ({state})",
            # Guarded on `seen` rather than indexing it blind: if the check above already failed
            # because nothing was written, an IndexError here would jump straight to the finally
            # block and this file would report no summary at all - hiding the very failure it
            # just caught.
            bool(seen) and seen[0][2].get("DynamicShadows") == ("True" if state else "False"),
            f"asked for {seen[0][2]!r}" if seen else "edit_ini was never called at all",
        )
    SH.edit_ini = real_edit_ini

    # --- the real round trip: on, watch it change, off, watch it restore -------------------

    whole_before = INI_PATH.read_text(encoding="latin-1")

    SH.enabled.value = not (before == "True")
    after_first = ini_value(INI_PATH, SH.SECTION, SH.KEY)
    check(
        "flipping the switch really changes the real file",
        after_first == ("False" if before == "True" else "True"),
        f"{before!r} -> {after_first!r}",
    )
    check(
        "light shafts were not touched by that write",
        ini_value(INI_PATH, SH.SECTION, "bAllowLightShafts") == light_before,
        f"bAllowLightShafts is now {ini_value(INI_PATH, SH.SECTION, 'bAllowLightShafts')!r}, "
        f"was {light_before!r}",
    )

    SH.enabled.value = (before == "True")
    after_second = ini_value(INI_PATH, SH.SECTION, SH.KEY)
    check(
        "flipping it back restores the original value",
        after_second == before,
        f"back to {after_second!r}, started at {before!r}",
    )
    check(
        "the two writes left every other byte of the file exactly as it was",
        INI_PATH.read_text(encoding="latin-1") == whole_before,
        f"{len(whole_before)} bytes before, "
        f"{len(INI_PATH.read_text(encoding='latin-1'))} after",
    )

    # --- empty/error scenarios, against the pure function so nothing real is at risk -------

    NO_SECTION = ["[SomeOtherSection]\r\n", "SomeKey=1\r\n"]
    _, changed, missing = gf.apply_ini_edits(NO_SECTION, SH.SECTION, {SH.KEY: "True"})
    check(
        "a file with no [SystemSettings] section at all reports the section missing, not the key",
        changed == {} and missing == [f"{SH.SECTION} (no such section)"],
        f"changed={changed}, missing={missing}",
    )

    NO_KEY = ["[SystemSettings]\r\n", "SomeOtherKey=1\r\n"]
    _, changed, missing = gf.apply_ini_edits(NO_KEY, SH.SECTION, {SH.KEY: "True"})
    check(
        "a section with no DynamicShadows key reports the key missing",
        changed == {} and missing == [SH.KEY],
        f"changed={changed}, missing={missing}",
    )

    ALREADY_RIGHT = ["[SystemSettings]\r\n", "DynamicShadows=True\r\n"]
    _, changed, missing = gf.apply_ini_edits(ALREADY_RIGHT, SH.SECTION, {SH.KEY: "True"})
    check(
        "asking for a value the sample already has changes nothing and reports nothing missing",
        changed == {} and missing == [],
        f"changed={changed}, missing={missing}",
    )

    # --- wiring ------------------------------------------------------------------------------

    check(
        "the callback is installed as on_change_anytime, the one that actually fires",
        SH.enabled.on_change_anytime is SH._on_change,
        f"on_change_anytime={SH.enabled.on_change_anytime!r}",
    )

    feature = next((f for f in core.all_features() if f.name == "Dynamic shadows"), None)
    check(
        "the dynamic shadows feature loaded",
        feature is not None and feature.failed is None,
        feature.failed if feature else "no feature by that name",
    )
    if feature is not None:
        check(
            "the core can re-run it when it re-applies game data",
            feature.apply is not None,
            "apply is None: nothing would ever run this at the main menu",
        )
        check(
            "it is marked as writing game data, so the main-menu pass includes it",
            feature.writes_game_data,
            f"writes_game_data={getattr(feature, 'writes_game_data', None)}",
        )

finally:
    SH.edit_ini = real_edit_ini
    if SH.enabled.value != was:
        SH.enabled.value = was
    final = ini_value(INI_PATH, SH.SECTION, SH.KEY)
    check(
        "the switch and the real file both ended up back where they started",
        SH.enabled.value == was and final == before,
        f"switch={SH.enabled.value!r}, file reads {final!r}, started at {before!r}",
    )

summary()
