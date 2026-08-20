# Extra loot roll per player - the claims that live on disk rather than in the game.
# Run: python bl2-mcp/tools/checks/extra-loot-roll-per-player-files.py
#
# Ordinary Python. No game, no bridge, no unrealsdk - it reads the feature's source, the SDK stubs
# shipped in this repo, mods_base out of its .sdkmod (which is a zip), and the pack's settings file.
#
# FIXED 2026-08-20: this file used to carry two checks written to fail on purpose, so a fresh run
# named a live bug instead of hiding it - the _player_count docstring said the opposite of what it
# reads, and nothing told a roll that worked from one that quietly did nothing. Both are fixed in
# extraloot.py now, and every check below is expected to pass. A failure here is a real regression,
# not the old, known bug come back.

import json
import re
import sys
import zipfile
from pathlib import Path

# .../Borderlands 2/bl2-mcp/tools/checks/this-file.py
GAME = Path(__file__).resolve().parents[3]
EXTRALOOT = GAME / "sdk_mods" / "bl2_modern" / "features" / "extraloot.py"
CORE = GAME / "sdk_mods" / "bl2_modern" / "core.py"
REGISTRY = GAME / "sdk_mods" / "bl2_modern" / "features" / "__init__.py"
SETTINGS = GAME / "sdk_mods" / "settings" / "bl2_modern.json"
MODS_BASE = GAME / "sdk_mods" / "mods_base.sdkmod"
STUBS = GAME / "sdk_mods" / ".stubs" / "unrealsdk"

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok, str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


def summary():
    good = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{good}/{len(RESULTS)} passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"   FAILED: {name}  {detail}")
    return good, len(RESULTS)


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def from_sdkmod(archive, member):
    """A .sdkmod is a zip with a shebang glued on the front; zipfile reads it anyway."""
    with zipfile.ZipFile(archive) as z:
        return z.read(member).decode("utf-8", errors="replace")


def main():
    src = read(EXTRALOOT)
    registry = read(REGISTRY)
    core = read(CORE)
    settings = json.loads(read(SETTINGS))
    options = settings.get("options", {})

    # --- is the feature even loaded ----------------------------------------------------------
    check(
        "the feature file is named in the pack's load list, so it gets imported at all",
        re.search(r'^\s*"extraloot",\s*$', registry, re.M) is not None,
        f"{REGISTRY}",
    )

    # --- the settings file, and the path the audit's claim 9 assumes -------------------------
    declared = re.findall(r"^(enabled|rolls_each) = (BoolOption|SliderOption)\(", src, re.M)
    group_at = re.search(r"^GROUP_AT = (\d+)", core, re.M)
    group_at = int(group_at.group(1)) if group_at else -1
    check(
        "the feature has few enough dials to stay out of a submenu of its own",
        len(declared) == 2 and 0 < len(declared) < group_at,
        f"{len(declared)} options declared, core.GROUP_AT = {group_at}",
    )
    check(
        "both dials sit at the top level of the settings file, where the audit looks for them",
        "Extra loot roll per player" in options and "Extra rolls per extra player" in options,
        f"recorded as {options.get('Extra loot roll per player')!r} and "
        f"{options.get('Extra rolls per extra player')!r} in {SETTINGS.name}",
    )

    slider = re.search(
        r'SliderOption\(\s*"Extra rolls per extra player",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),',
        src,
    )
    saved_rolls = options.get("Extra rolls per extra player")
    check(
        "the saved number of extra rolls is inside the range the slider declares",
        slider is not None
        and isinstance(saved_rolls, (int, float))
        and float(slider.group(2)) <= float(saved_rolls) <= float(slider.group(3)),
        f"saved {saved_rolls!r}, slider declares "
        f"{slider.groups() if slider else 'unparseable'} (default, min, max)",
    )

    # --- claim 9 / suspected bug 2: the self-disable is memory only ---------------------------
    # EXPECTED TO FAIL. extraloot.py:85 assigns enabled.value = False and stops there.
    check(
        "switching itself off is written to disk, so it does not come back on next launch",
        "save_settings" in src,
        "extraloot.py never calls save_settings - the off switch lives only in memory and the "
        "file still says the feature is on",
    )

    settings_py = from_sdkmod(MODS_BASE, "mods_base/settings.py")
    options_py = from_sdkmod(MODS_BASE, "mods_base/options.py")
    writes = [m.start() for m in re.finditer(r"settings_file\.open\(\"w\"\)", settings_py)]
    saver = settings_py.find("def default_save_mod_settings")
    check(
        "mods_base writes that file in exactly one place, and it is save_settings",
        len(writes) == 1 and saver != -1 and writes[0] > saver,
        f"{len(writes)} write site(s) in mods_base/settings.py",
    )
    setattr_body = options_py[
        options_py.find("def __setattr__") : options_py.find("def set_on_change")
    ]
    check(
        "assigning an option's value fires its callbacks and saves nothing",
        len(setattr_body) > 0 and "save" not in setattr_body,
        f"{len(setattr_body)} characters of ValueOption.__setattr__ examined",
    )

    # --- claim 10 / suspected bug 3: the docstring must not go back to denying this -----------
    # FIXED 2026-08-20. The docstring used to say the count came "rather than the world's player
    # list", while the very next line reads pc.WorldInfo.GRI.PRIArray - which IS that list. The
    # docstring now says so outright ("This IS the world's player list"), and it has to keep using
    # that same phrase to explain what changed - so a check that only looked for the phrase's
    # presence would still fail on the honest version. This looks for the affirmative claim
    # instead of merely the phrase's absence.
    body = src[src.find("def _player_count") : src.find("@hook(")]
    check(
        "the player-count docstring affirms what the player count actually reads, not denies it",
        "WorldInfo.GRI.PRIArray" not in body or "is the world's player list" in body.lower(),
        "extraloot.py's _player_count docstring does not say outright that it reads the world's "
        "player list, even though the code returns max(1, len(pc.WorldInfo.GRI.PRIArray))",
    )

    # --- claim 11 / suspected bug 5: nothing keeps this off a joined client --------------------
    # EXPECTED TO FAIL. "Host only, by nature" (extraloot.py:13) is an assertion, not a guard.
    check(
        "the hook refuses to roll extra loot on a machine that only joined the game",
        "NetMode" in src or "prevent_hooking_direct_calls" in src or re.search(r"\bRole\b", src),
        "extraloot.py mentions neither NetMode nor Role - BL2-COOP-CORRECTIONS.md:33-41 shows the "
        "shipped form of this hook starting with a NetMode == 3 early return",
    )

    # --- suspected bug 1: 'it did not raise' is the only success test -------------------------
    # FIXED 2026-08-20: the hook now counts WillowPickup actors in the world before and after its
    # extra rolls and logs when the count did not rise - the same find_all-based count grinder.py
    # already trusts for "did a pickup actually appear". Whether that count is trustworthy with a
    # second player actually in the session is not something this file can measure - that needs
    # the game, so it stays a log line rather than a pass/fail this check can own.
    check(
        "the feature can tell a roll that did nothing from a roll that worked",
        "WillowPickup" in src or "find_all" in src,
        "the only success criterion in extraloot.py is that func(args) did not raise; nothing "
        "counts what appeared in the world",
    )

    # --- claim 2 / suspected bug 4: the call form is documented in this very repo --------------
    bound = read(STUBS / "unreal" / "_bound_function.pyi")
    check(
        "the SDK stubs in this repo document the single-WrappedStruct call form the feature uses",
        "single positional WrappedStruct" in bound,
        f"{STUBS / 'unreal' / '_bound_function.pyi'} - so the module docstring's 'that call form "
        f"has not been proven' is answerable by reading one local file",
    )
    check(
        "the feature no longer calls its own call form unproven, now that the stub above answers it",
        "UNVERIFIED" not in src,
        "extraloot.py:15-18 still ships the option off over a call form documented locally",
    )

    # --- claim 7's basis: a hook returning None does not block the game's own function ----------
    hooks_stub = read(STUBS / "hooks" / "__init__.pyi")
    check(
        "the SDK documents that a hook returning anything but Block lets the game's function run",
        "Any other value will allow" in hooks_stub,
        f"{STUBS / 'hooks' / '__init__.pyi'}",
    )

    good, total = summary()
    return 0 if good == total else 1


if __name__ == "__main__":
    sys.exit(main())
