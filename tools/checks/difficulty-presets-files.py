# Difficulty presets, the half that lives on disk - claims from AUDIT-RAW/difficulty-presets.md
# Run: python bl2-mcp/tools/checks/difficulty-presets-files.py
#
# ORDINARY PYTHON. No game, no bridge, no harness - so it has its own check()/summary()
# below. Everything it reads is a file: the preset arithmetic (which imports nothing), the
# Community Patch's own text, the feature list, and the machine-wide settings file.

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[3]
PACK = GAME / "sdk_mods" / "bl2_modern"
PATCH = PACK / "data" / "patch.txt"
SETTINGS = GAME / "sdk_mods" / "settings" / "bl2_modern.json"

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


def load(path, name):
    """Import a file that has no game imports, without importing the package around it."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    dm = load(PACK / "difficulty.py", "bl2_difficulty_numbers")
    pf = load(PACK / "patchfile.py", "bl2_patchfile")

    # --- claim 1: the file's own self-test still passes ------------------------------
    run = subprocess.run(
        [sys.executable, "difficulty.py"],
        cwd=PACK,
        capture_output=True,
        text=True,
    )
    check(
        "the preset arithmetic passes its own self-test",
        run.returncode == 0 and "difficulty: all checks passed" in run.stdout,
        f"exit {run.returncode}, last line "
        f"{(run.stdout.strip().splitlines() or ['(nothing)'])[-1]!r}"
        + (f", stderr {run.stderr.strip()[:200]!r}" if run.stderr.strip() else ""),
    )

    # The self-test cross-compares the presets at THREE tiers only - it builds them with
    # preset(name, 1), whose count defaults to 3 (difficulty.py:255). The game the pack
    # actually ships into has four, because the Community Patch rewrites this property, so
    # the count that matters is the one nothing was comparing.
    same = []
    for count in (1, 2, 3, 4, 5, 6, 8):
        built = {n: dm.preset(n, 1, count) for n in dm.CHOICES if dm.PRESETS[n] is not None}
        same += [
            f"{a} == {b} at {count} tiers"
            for a in built
            for b in built
            if a < b and built[a] == built[b]
        ]
    check(
        "no two presets are the same numbers at any tier count the game might report",
        not same,
        f"identical pairs: {same}" if same else "checked 1, 2, 3, 4, 5, 6 and 8 tiers",
    )

    # --- claim 13's other half: what the slider does to the spacing -------------------
    # The menu calls the setting "the level these rules begin applying at" and says nothing
    # about the bands. LATER_LEVELS[0] is 25, which loses to levels[-1] + 1 = 51, so the
    # game's own 50/61/72 spacing collapses to one level apart.
    levels = dm.custom_levels(50, 3)
    check(
        "starting the rules at 50 leaves the tier bands where the game itself puts them",
        levels == [50, 61, 72],
        f"custom_levels(50, 3) is {levels}; UVHM's distinct first-tier damage multiplier "
        f"then covers {levels[1] - levels[0]} level(s) instead of 11",
    )

    # --- claim 21: the sliders' bottom end -------------------------------------------
    # _pct (features/difficulty.py:66-73) gives every Custom slider a minimum of 0, and
    # check() validates field names and tier levels but never magnitudes, so a player can
    # select a 0x enemy health multiplier and nothing refuses it. This check exists to
    # force the decision, not to guess it.
    zeroed = dm.custom(1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4)
    try:
        dm.check(zeroed, 4)
        refused = False
    except ValueError:
        refused = True
    check(
        "the validator refuses a preset built from the Custom sliders' 0% end",
        refused,
        "check() accepted every multiplier at 0.0 - the sliders' declared minimum is 0",
    )

    # --- claims 4 and 20: the Community Patch's own write ----------------------------
    text = PATCH.read_text(encoding="utf-8", errors="replace")
    commands, hotfixes, _ = pf.commands_from(text)
    target = f"{dm.TARGET} {dm.PROPERTY}"
    writes = [c for c in commands if target in c]
    check(
        "exactly one command the patch ships switched on rewrites the tuning table",
        len(writes) == 1,
        f"{len(writes)} enabled writes of {target} among {len(commands)} commands",
    )
    check(
        "no hotfix rewrites the tuning table, so nothing re-clobbers it on a level load",
        not [c for _, c in hotfixes if target in c],
        f"{len(hotfixes)} hotfixes in the patch, "
        f"{len([c for _, c in hotfixes if target in c])} of them touching {target}",
    )

    # --- tickets 21 and 27: Nifsara's slag against the bundled Community Patch ----------
    # The whole file, sections switched off and hotfixes included, in both the set form and
    # the hotfix form - so a patch section turned on later cannot start fighting the switch.
    # Every line of his section, the class-loaded ones (turret, Deathtrap, Double Up) included.
    slag_lines = dm.SLAG_SECOND_WIND + dm.SLAG_CLASS_SECOND_WIND
    slag_hits = []
    for command in slag_lines:
        obj, prop = command.split(" ")[1:3]
        slag_hits += [form for form in (f"{obj} {prop}", f"{obj},{prop},") if form in text]
    check(
        "nothing in the Community Patch writes what the Second Wind slag switch writes",
        not slag_hits and len(slag_lines) == 15,
        f"collisions: {slag_hits}" if slag_hits else
        f"none of the {len(slag_lines)} properties {[' '.join(c.split(' ')[1:3]) for c in slag_lines]} "
        f"appears anywhere in the patch",
    )
    # The same objects written for other properties are not collisions, but they are named, so a
    # new one shows up here rather than nowhere.
    shared = sorted({
        f"{obj} {prop}"
        for obj in {c.split(" ")[1] for c in slag_lines}
        for prop in re.findall(rf"set {re.escape(obj)} (\w+)", text)
    })
    check(
        "the patch writes the slag objects only for their colours and Double Up's effects",
        shared == [
            "GD_Amp.DamageType.DmgType_Amp_Impact DamageColor",
            "GD_Amp.DamageType.DmgType_Amp_Status DamageColor",
            "GD_Soldier_Skills.Guerrilla.DoubleUp SkillEffectDefinitions",
        ],
        f"the patch also writes {shared}",
    )

    if writes:
        command = writes[0]
        tiers = re.findall(r"MinEffectiveLevel=(\d+)", command)
        scales = re.findall(
            r"HealthPassiveRegenerationRate'.*?BaseValueScaleConstant=([0-9.]+)\)",
            command,
        )
        check(
            "the patched table still carries a healing entry in every one of its tiers",
            len(tiers) == 4 and len(scales) == 4,
            f"tiers at {tiers}, {len(scales)} healing entries",
        )
        check(
            "the healing rates the feature has to put back are still 1.0 / 1.0 / 1.25 / 1.0",
            [float(s) for s in scales] == [1.0, 1.0, 1.25, 1.0],
            f"scales {[float(s) for s in scales]}",
        )

    # --- claim 20, the ordering half -------------------------------------------------
    features = (PACK / "features" / "__init__.py").read_text(encoding="utf-8")
    order = re.findall(r'"([a-z]+)",', features.split("FEATURES = [", 1)[-1])
    check(
        "the Community Patch feature is listed before the difficulty feature",
        "communitypatch" in order
        and "difficulty" in order
        and order.index("communitypatch") < order.index("difficulty"),
        f"feature order {order}",
    )

    # --- claim 18: the machine-wide settings file ------------------------------------
    # The audit says this file reads 'Normal'. It does not - it reads whatever the menu was
    # last left on. The point that survives is the one worth checking: a value in here that
    # the build cannot build is a silent no-op, because _apply logs and returns
    # (features/difficulty.py:192-194).
    saved = json.loads(SETTINGS.read_text(encoding="utf-8"))["options"]["Difficulty presets"]
    known = [*dm.CHOICES, "Custom"]
    # Absent is fine since ticket 27: the preset is per character, and it is written out only for
    # a character that chose, so a settings save while one that never chose is loaded leaves it out.
    check(
        "the preset saved in the machine-wide settings file is one this build can build, or none",
        saved.get("Difficulty preset", "Normal") in known,
        f"settings file says {saved.get('Difficulty preset', '(nothing)')!r}, this build knows {known}",
    )

    # A renamed option identifier drops the saved value on the floor without a word, so
    # every name in the settings file has to still appear in the feature that declares it.
    # The six percentage sliders are built by _pct(), which glues "Custom: " onto the name
    # it is passed (features/difficulty.py:67), so the tail is what appears in the source.
    source = (PACK / "features" / "difficulty.py").read_text(encoding="utf-8")
    orphans = [
        name
        for name in saved
        if f'"{name}"' not in source and f'"{name.split(": ", 1)[-1]}"' not in source
    ]
    check(
        "every setting saved for this feature still matches an option the feature declares",
        not orphans,
        f"orphaned settings: {orphans}" if orphans else f"{len(saved)} settings, all matched",
    )


if __name__ == "__main__":
    main()
    summary()
