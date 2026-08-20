# Extras - the claims about files on disk, from AUDIT-RAW/extras.md
# Run: python bl2-mcp/tools/checks/extras-and-scaling-files.py
#
# Ordinary Python, outside the game. No harness, no unrealsdk. It imports build_extras.py and
# patchfile.py straight off disk, because importing the bl2_modern package would pull in
# mods_base, which only exists inside the game.
#
# Until 2026-08-20 one check here was written to FAIL on purpose, because the claim it carried
# was false: extras.py:8-11 says sharing SOURCES with build_extras makes an invisible switch
# impossible, and build_extras.py used to print a warning and carry on when a source file was
# missing - exactly how you get one. build_extras.build() now raises instead, so the check below
# tests the fix rather than documenting the bug.

import importlib.util
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3] / "sdk_mods" / "bl2_modern"

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


def summary():
    good = sum(1 for _n, ok, _d in RESULTS if ok)
    print(f"\n{good}/{len(RESULTS)} passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"   FAILED: {name}  {detail}")
    return good, len(RESULTS)


def _load(name):
    """Import one file out of bl2_modern without importing the package around it."""
    spec = importlib.util.spec_from_file_location(f"_checks_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    sys.path.insert(0, str(ROOT))  # build_extras falls back to `from patchfile import ...`
    patchfile = _load("patchfile")
    build_extras = _load("build_extras")

    extras_txt = ROOT / "data" / "extras.txt"
    check(
        "the extras file the pack ships is on disk",
        extras_txt.is_file(),
        str(extras_txt),
    )
    if not extras_txt.is_file():
        return summary()

    text = extras_txt.read_text(encoding="utf-8")
    found = patchfile.sections_in(text)
    wanted = [section for _file, section, _what in build_extras.SOURCES]

    # Claim 1. This is the assert patchsections.py:136-137 already makes for the Community
    # Patch and that nothing has ever made for extras.txt.
    invisible = [section for section in wanted if section not in found]
    check(
        "every switch in the extras menu names a section that really is in extras.txt",
        not invisible,
        f"sections on disk: {found}; switches with no section: {invisible}",
    )

    orphaned = [section for section in found if section not in wanted]
    check(
        "every section in extras.txt has a switch, so nothing in the file is unreachable",
        not orphaned,
        f"sections with no switch: {orphaned}",
    )

    commands, hotfixes, ignored = patchfile.commands_from(text)
    gated = sorted(level for level, _c in hotfixes if level not in ("None", ""))

    # DERIVED. This used to hardcode "36 commands across four sections, four tied to a map" -
    # a snapshot of the file the day it was written. Adding "Faster animations" (2026-08-20)
    # took the real numbers to 2951 commands across 5 sections, 2460 of them tied to a map,
    # and every future source added to SOURCES would go stale the same way. What actually has
    # to hold never changes: one section per SOURCES entry, so a build can never ship a
    # switch with nothing behind it, and the two independent ways of counting - sections_in's
    # per-category tally and commands_from's flat list - agree on the grand total. How many
    # end up map-gated is a property of what the source mods happen to contain, not something
    # to assert an exact number for; it is only reported below.
    check(
        "the file holds one section per SOURCES entry, and both ways of counting the file "
        "agree on the total",
        len(found) == len(wanted) and sum(found.values()) == len(commands) + len(hotfixes),
        f"{len(found)} sections against {len(wanted)} in SOURCES; {len(commands)} commands + "
        f"{len(hotfixes)} hotfixes ({len(gated)} map-gated across {len(set(gated))} maps) = "
        f"{len(commands) + len(hotfixes)}, against sections_in's {sum(found.values())} total; "
        f"{ignored} lines ignored",
    )

    # Claim 2, FIXED 2026-08-20. build_extras.build() used to print a warning and carry on
    # when a source file was missing - the switch is still built from SOURCES regardless, so
    # a silently skipped section is exactly the invisible switch extras.py:8-11 says cannot
    # happen. It now raises instead, so a build pointed at the wrong folder cannot ship a
    # smaller file without saying so - which also retires the old second half of this claim
    # (whether the round-trip assert in __main__ could catch a section that quietly vanished):
    # build() never gets the chance to return an incomplete `counts` for that assert to miss,
    # because it never returns at all when a source is missing.
    with tempfile.TemporaryDirectory() as empty:
        try:
            build_extras.build(pathlib.Path(empty))
            raised = None
        except Exception as ex:  # noqa: BLE001 - the check is *what* it raises, if anything
            raised = ex
    check(
        "building from a folder with none of the source files raises instead of shipping an "
        "invisible switch",
        isinstance(raised, FileNotFoundError),
        f"build() from an empty folder raised {raised!r}" if raised is not None
        else "build() returned normally instead of raising - every one of "
        f"{len(build_extras.SOURCES)} switches would sit in the menu with no section behind it",
    )

    # levelscaling.py:71-73 and coopfixes.py:74-77 both say the deprecated on_change arg is
    # avoided. The log carries two DeprecationWarnings from `<string>:14` and `:16`, which is
    # code compiled from a string - not from any file in this pack. This proves which half.
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bon_change\s*=", line):
                offenders.append(f"{path.name}:{number}")
    check(
        "no file in the pack passes the deprecated on_change argument to an option",
        not offenders,
        f"{len(list(ROOT.rglob('*.py')))} files scanned; offenders: {offenders}",
    )

    return summary()


if __name__ == "__main__":
    good, total = main()
    sys.exit(0 if good == total else 1)
