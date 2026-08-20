"""
Level-less gear - the claims that live on disk, checked outside the game.

    python bl2-mcp/tools/checks/level-less-gear-files.py

Ordinary python: no harness, no unrealsdk, nothing running. The one thing on disk that can be
checked about "the marked list is stored per character" is the NEGATIVE half - that the list is
not in the machine-wide mod settings file. The positive half lives inside the character save,
and BL2 saves are compressed, so `Level-less items` is not findable in the bytes (measured: the
string appears in none of the four .sav files). Proving the list is really in there needs a
character reload - see level-less-gear-needs-travel.py.
"""

import json
import re
from pathlib import Path

GAME = Path(r"D:/SteamLibrary/steamapps/common/Borderlands 2")
SETTINGS = GAME / "sdk_mods" / "settings" / "bl2_modern.json"
LEVELLESS = GAME / "sdk_mods" / "bl2_modern" / "features" / "levelless.py"
SAVE_OPTIONS = GAME / "sdk_mods" / "save_options.sdkmod"
SAVES = Path.home() / "Documents" / "My Games" / "Borderlands 2" / "WillowGame" / "SaveData"

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok, str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


def summary():
    good = sum(1 for _n, ok, _d in RESULTS if ok)
    print(f"\n{good}/{len(RESULTS)} passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"   FAILED: {name}  {detail}")
    return good, len(RESULTS)


def main():
    check(
        "the pack's machine-wide settings file is on disk and readable",
        SETTINGS.is_file(),
        str(SETTINGS),
    )

    text = SETTINGS.read_text(encoding="utf-8") if SETTINGS.is_file() else ""
    try:
        data = json.loads(text) if text else None
        parsed = data is not None
    except Exception as ex:
        data, parsed = None, False
        print(f"   settings json would not parse: {ex!r}")
    check(
        "the machine-wide settings file is valid json",
        parsed,
        f"{len(text)} bytes, top-level keys {sorted(data) if isinstance(data, dict) else 'n/a'}",
    )

    # Claim 12, negative half: a per-character list must not be sitting in the file that is
    # shared by every character on this machine.
    check(
        "the marked list is not written into the machine-wide settings file",
        "Level-less" not in text,
        f"searched {SETTINGS.name} for 'Level-less'; found "
        f"{[line.strip() for line in text.splitlines() if 'Level-less' in line]}",
    )

    # Suspected bug 4: the hand-rolled _HiddenSaveOption.
    src = LEVELLESS.read_text(encoding="utf-8") if LEVELLESS.is_file() else ""
    check(
        "the levelless source is on disk where the audit says it is",
        bool(src),
        str(LEVELLESS),
    )

    shipped = ""
    if SAVE_OPTIONS.is_file():
        import zipfile

        with zipfile.ZipFile(SAVE_OPTIONS) as archive:
            shipped = archive.read("save_options/options.py").decode("utf-8")
    check(
        "save_options already ships a hidden per-character option class",
        bool(re.search(r"^class HiddenSaveOption", shipped, re.M)),
        f"{SAVE_OPTIONS.name}: "
        f"{'found class HiddenSaveOption' if 'HiddenSaveOption' in shipped else 'not found'}",
    )
    check(
        "levelless.py uses that shipped class instead of hand-rolling its own",
        re.search(r"^\s*class _HiddenSaveOption", src, re.M) is None,
        "levelless.py:51-52 defines its own _HiddenSaveOption. The shipped one differs in one "
        "way that matters: it overrides save() to write the character save, where the "
        "hand-rolled one inherits HiddenOption.save(), which writes the machine-wide settings "
        "file - or raises, because levelless.py:247 never gives the option a mod",
    )

    # Where the per-character half actually lives, so a person can find it.
    sav = sorted(SAVES.rglob("Save*.sav")) if SAVES.is_dir() else []
    check(
        "there is at least one character save file for the list to live in",
        bool(sav),
        f"{len(sav)} under {SAVES}: {[f.name for f in sav[:6]]}",
    )
    for path in sav:
        raw = path.read_bytes()
        if b"Level-less" in raw:
            print(f"   note: {path.name} carries the string in plain bytes")

    summary()


if __name__ == "__main__":
    main()
