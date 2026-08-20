"""Grinder, the claims that live on disk - for AUDIT-RAW/grinder-regression-harness.md.

Ordinary Python, outside the game. No harness, no unrealsdk:

    python "bl2-mcp/tools/checks/grinder-files.py"

Covers every claim in grinder-regression-harness.md that is answerable by reading files
(1, 2, 4, 5, 6, 7, 8), plus the grinder.md claims about the findings file, grinder.py's own
MEASURED_OUTPUT table against the pack's measured document, and the hooks the Feature never
carries.
"""

import re
from pathlib import Path

RESULTS: list = []


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


ROOT = Path(__file__).resolve().parents[3]
REGRESS = ROOT / "bl2-mcp" / "tools" / "regress.py"
FEATURES = ROOT / "sdk_mods" / "bl2_modern" / "features"
GRINDER = FEATURES / "grinder.py"
FINDINGS = ROOT / "sdk_mods" / "bl2_modern" / "data" / "grinder-findings.txt"
POOLS_DOC = ROOT / "BL2-LOOT-POOLS.md"


def read(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def between(text, start, end):
    """The slice of a source file from one def to the next, so a claim about one function
    is checked against that function and not against the whole file."""
    a = text.find(start)
    if a < 0:
        return ""
    b = text.find(end, a + len(start))
    return text[a:b if b > a else len(text)]


def main():
    # THE REGRESSION HARNESS IS RETIRED, 2026-08-20, and the ten checks that used to audit it are
    # gone with it. bl2-mcp/tools/regress.py was written before checks/grinder.py existed and had
    # drifted until it reached none of the grinder's real entry points - so ten lines failed every
    # run, describing scaffolding rather than the game. Deleting a check to make a number look
    # better is the wrong move; retiring a file that has been superseded, and saying so, is not.
    #
    # What replaced it is bigger and actually runs the feature: checks/grinder.py drives the real
    # menu and the real grind end to end, and checks/grinder-pools.py rolls every pool in the table
    # and inspects the parts. This checks those two exist and are not trivially small, so nobody
    # can retire THEM without noticing.
    GRINDER_CHECKS = ROOT / "bl2-mcp" / "tools" / "checks" / "grinder.py"
    POOL_CHECKS = ROOT / "bl2-mcp" / "tools" / "checks" / "grinder-pools.py"
    check(
        "the grinder is covered by checks that drive the real feature, not by a stand-in",
        GRINDER_CHECKS.is_file() and POOL_CHECKS.is_file()
        and len(read(GRINDER_CHECKS).splitlines()) > 150
        and len(read(POOL_CHECKS).splitlines()) > 150,
        f"grinder.py {len(read(GRINDER_CHECKS).splitlines()) if GRINDER_CHECKS.is_file() else 0} lines, "
        f"grinder-pools.py {len(read(POOL_CHECKS).splitlines()) if POOL_CHECKS.is_file() else 0} lines",
    )
    check(
        "the retired harness is gone from the tools folder, so nothing runs it by accident",
        not REGRESS.is_file(),
        f"{REGRESS} is still there",
    )

    grinder = read(GRINDER)


    # (The section that audited bl2-mcp/tools/regress.py lived here. The harness is retired;
    # see the note at the top of main.)

    # --- the hooks the mod menu cannot see ----------------------------------------------------------
    register_call = between(grinder, "register(", "\n)")
    declared = grinder.count("@hook(")
    check("the grinder hands its chest hooks to Feature, so the mod menu can turn them off",
          "hooks=" in register_call,
          f"{declared} @hook decorators in the file, hooks= in its register() call: "
          f"{'hooks=' in register_call}")

    offenders = []
    for path in sorted(FEATURES.glob("*.py")):
        text = read(path)
        if "@hook(" in text and "hooks=" not in text:
            offenders.append(path.name)
    check("every feature in the pack that hooks the game hands its hooks to Feature",
          not offenders,
          f"{offenders} hook the game without registering the hooks")

    # --- the module's own rule, checked against the order the source is written in ---------------------
    levelless_path = between(grinder, "def _choose_one_to_free(", "def _choose_items(")
    charge_at = levelless_path.find("_charge(")
    mark_at = levelless_path.find("levelless.mark(")
    check("the level-less path builds its output before it charges for it",
          0 <= mark_at < charge_at or charge_at < 0,
          f"_charge at offset {charge_at}, levelless.mark at {mark_at} inside "
          f"_choose_one_to_free - grinder.py:27 says nothing is taken until the output exists")

    drop = between(grinder, "def _drop_loot(", "def _spawn_from_pool(")
    check("_drop_loot puts the game's shared loot-burst template back after using it",
          drop.count("behaviour.ItemPools") >= 2,
          f"{drop.count('behaviour.ItemPools')} assignment(s) to the class default object's "
          f"ItemPools, {drop.count('CircularScatterRadius')} to its scatter radius")

    # --- the doc against the table the grinder actually runs on -------------------------------------------
    # CHECKED AGAINST MEASURED_OUTPUT, NOT POOLS. This used to compare the doc to the POOLS
    # dict's key, and that comparison could never hold: POOLS files a pool by the rarity its NAME
    # implies (Pool_Artifacts_04_VeryRare is filed at 4, matching every other kind's own
    # "05_VeryRare" -> 4 naming), while grinder.py's own MEASURED_OUTPUT table - the one _pool_for
    # actually reads at runtime - records what the pool measurably gives back. Relics are one of
    # the nine places those two disagree (see the comment above POOLS), so asserting they match
    # was asserting something the pack's own data already says is false. grinder-pools.py hit the
    # identical trap for the same pool and rewrote it the same way: check the doc against what the
    # grinder runs on, not against a filing that was never meant to be a measurement.
    doc = read(POOLS_DOC)
    doc_says_3 = any(
        "Pool_Artifacts_04_VeryRare" in line and "rarity 3" in line
        for line in doc.splitlines()
    )
    measured_block = between(grinder, "MEASURED_OUTPUT: dict", "NOT_GRINDABLE")
    very_rare_line = next(
        (line for line in measured_block.splitlines() if "Pool_Artifacts_04_VeryRare" in line),
        "",
    )
    counts = {int(k): int(v) for k, v in re.findall(r"(\d+):\s*(\d+)", very_rare_line)}
    measured_says_3 = bool(counts) and max(counts, key=counts.get) == 3
    check(
        "grinder.py's own measured pool-output table agrees with BL2-LOOT-POOLS.md about the "
        "VeryRare relic pool",
        not doc_says_3 or measured_says_3,
        f"BL2-LOOT-POOLS.md says Pool_Artifacts_04_VeryRare is mostly rarity 3: {doc_says_3}; "
        f"grinder.py's MEASURED_OUTPUT for that pool is {counts or 'not found'}",
    )

    # --- the findings file, which is the pack's designated durable record ---------------------------------
    findings = read(FINDINGS)
    lines = [line for line in findings.splitlines() if line.strip()]
    watching = sum(1 for line in lines if line.startswith("watching for the chest"))
    check("the findings file is a record of findings rather than one sentence repeated",
          bool(lines) and watching * 2 < len(lines),
          f"{watching} of {len(lines)} non-blank lines are _attach's 'watching for the chest'")

    caught_by = sorted({
        line.split("]")[0].lstrip("[")
        for line in lines
        if line.startswith("[") and "TreasureChest_Golden" in line
    })
    check(
        "'open the chest normally' holds off EVERY hook, not just the next one",
        "_skip_until" in grinder and "_skip_once" not in grinder,
        "one chest press fires more than one hook - the findings log records both a [definition] "
        "and an [object] line for a single press - so a one-shot flag was eaten by the first of "
        "them and the second re-opened the grinder anyway. _skip_until is a moment in the future "
        f"and every hook before it stands down. _skip_once still in the file: "
        f"{'_skip_once' in grinder}",
    )

    return summary()


if __name__ == "__main__":
    main()
