"""Community Patch - the claims that live on disk, from AUDIT-RAW/community-patch.md.

Run: python bl2-mcp/tools/checks/community-patch-files.py

Ordinary Python. No game, no unrealsdk, no harness - so it has its own check()/summary() below.
It reads three things: the shipped patch.txt, the settings file the pack saved, and the live
unrealsdk.log (which is truncated per launch, so it holds exactly one launch).

The log checks are the only ones here that depend on the game having got as far as the main menu.
If it is mid-boot they will fail; re-run once it has settled rather than believing them.
"""

import json
import pathlib
import re
import sys

GAME = pathlib.Path(r"Z:/SteamLibrary/steamapps/common/Borderlands 2")
MOD = GAME / "sdk_mods" / "bl2_modern"
SETTINGS = GAME / "sdk_mods" / "settings" / "bl2_modern.json"
LOG = GAME / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"

sys.path.insert(0, str(MOD))

from patchfile import PACKAGE, commands_from, section_of, sections_in  # noqa: E402
from patchsections import EXPECTED_COUNTS, EXTRAS, NOT_A_SWITCH, SECTIONS, all_names  # noqa: E402

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


# The four objects the in-game file hardcodes for the Hide damage numbers check.
DAMAGE_EMITTERS = {
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_0",
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_1",
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_3",
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_17",
}
HIDE_DAMAGE = "Hide Damage Numbers/Critical/Resist"


def targets(text, wanted):
    """Every (object, property) pair a set of sections would write, lower-cased."""
    commands, hotfixes, _ignored = commands_from(text, wanted)
    pairs = set()
    for command in commands + [c for _lvl, c in hotfixes]:
        parts = command.split(None, 3)
        if len(parts) >= 3 and parts[0].lower() == "set":
            pairs.add((parts[1].lower(), parts[2].split("[")[0].lower()))
    return pairs


def kind(when):
    if when.startswith(PACKAGE):
        return "package"
    return "everywhere" if when in ("None", "") else "map"


def sizes(text, wanted):
    """(plain lines run at the main menu, hotfixes by kind) for one set of sections."""
    commands, hotfixes, _ignored = commands_from(text, wanted)
    kinds = {k: sum(1 for w, _c in hotfixes if kind(w) == k) for k in ("everywhere", "map", "package")}
    return len(commands), len(hotfixes), kinds


def entry(when, command):
    """A hotfix the way BLCMM hands it to the game: (entry type, `when,object,property,,value`)."""
    pieces = command.split(None, 3)
    value = pieces[3] if len(pieces) > 3 else ""
    if kind(when) == "package":
        return "SparkOnDemandPatchEntry", f"{when[len(PACKAGE):]},{pieces[1]},{pieces[2]},,{value}"
    first = "" if kind(when) == "everywhere" else when
    return "SparkLevelPatchEntry", f"{first},{pieces[1]},{pieces[2]},,{value}"


def blcmm_compile(text):
    """
    What BLCMM itself compiled from this file, which patch.txt carries after </BLCMM>: its plain
    set lines, and its hotfix entries as (type, value) - Gearbox's own GBX_ ones left out.
    """
    tail = text.split("</BLCMM>", 1)[1].splitlines()
    plain, keys, values = [], [], []

    def strings(line):
        body = line[line.index("(") + 1 : line.rindex(")")]
        out, i = [], 0
        while i < len(body):
            if body[i] != '"':
                i += 1
                continue
            j, buf = i + 1, ""
            while j < len(body) and body[j] != '"':
                if body[j] == "\\" and j + 1 < len(body):
                    buf += body[j + 1]
                    j += 2
                    continue
                buf += body[j]
                j += 1
            out.append(buf)
            i = j + 1
        return out

    for line in tail:
        line = line.strip()
        if line.startswith("set Transient.SparkServiceConfiguration_0 Keys "):
            keys = strings(line)
        elif line.startswith("set Transient.SparkServiceConfiguration_0 Values "):
            values = strings(line)
        elif line.startswith("set ") and not line.startswith("set Transient."):
            plain.append(line)
    hotfixes = [(k.split("-", 1)[0], v) for k, v in zip(keys, values) if "GBX" not in k.upper()]
    return plain, hotfixes, len(keys), len(values)


def skipped_by_blcmm(text, wanted):
    """
    Counted apart from commands_from, on purpose: the lines of the wanted sections that BLCMM
    would not run either - a line a shipped-on section ships off, and the second and later
    options of a choose-one (MUT) group inside an opt-in extra (BLCMM ticks only the first).
    """
    category = re.compile(r'<category name="((?:[^"\\]|\\.)*)"([^>]*)>')
    lines = text.split("</BLCMM>", 1)[0].splitlines()
    on_sections, path = set(), []
    for raw in lines:
        line = raw.strip()
        found = category.search(line)
        if found:
            path.append(found.group(1))
        if "</category>" in line and path:
            path.pop()
        if not found and line.startswith("<code") and 'profiles="default' in line:
            on_sections.add(section_of(path))
    skipped, path, stack = 0, [], []
    for raw in lines:
        line = raw.strip()
        found = category.search(line)
        if found:
            path.append(found.group(1))
            parent = stack[-1] if stack else None
            if parent and parent["mut"]:
                parent["options"] += 1
            out = bool(parent) and (parent["out"] or (parent["mut"] and parent["options"] > 1))
            stack.append({"mut": 'MUT="true"' in found.group(2), "options": 0, "out": out})
        if "</category>" in line and path:
            path.pop()
            stack.pop()
        if found or not line.startswith("<code"):
            continue
        parent = stack[-1] if stack else None
        if parent and parent["mut"]:
            parent["options"] += 1
        out = bool(parent) and (parent["out"] or (parent["mut"] and parent["options"] > 1))
        section = section_of(path)
        if section not in wanted:
            continue
        if section in on_sections:
            skipped += 'profiles="default' not in line
        else:
            skipped += out
    return skipped


def main():
    patch = (MOD / "data" / "patch.txt").read_text(encoding="utf-8", errors="replace")
    extras = (MOD / "data" / "extras.txt").read_text(encoding="utf-8", errors="replace")
    saved = json.loads(SETTINGS.read_text(encoding="utf-8"))["options"]["Community Patch"]
    log = LOG.read_text(encoding="utf-8", errors="replace").splitlines()

    names = all_names()
    defaults = {name for name, _short, on, _what in SECTIONS if on}
    on_disk = {name for name in names if saved.get(name)}
    every_section = set(names)
    extras_sections = set(sections_in(extras))

    # --- claim 1: no switch is a dead menu row ------------------------------------------
    found = sections_in(patch)
    dead = [name for name in names if name not in found]
    check(
        "every one of the nineteen switches names a section that exists in patch.txt",
        len(names) == 19 and not dead,
        f"{len(names)} switches, {len(found)} sections in the file; dead rows: {dead}",
    )
    unlisted = sorted(set(found) - set(names) - NOT_A_SWITCH)
    check(
        "patch.txt has no section the menu cannot reach",
        not unlisted,
        f"unreachable: {unlisted}",
    )
    wrong_size = {
        name: (want, found.get(name, 0))
        for name, want in EXPECTED_COUNTS.items()
        if found.get(name, 0) != want
    }
    check(
        "no section has quietly grown or emptied out since the counts were written down",
        not wrong_size,
        f"expected vs found: {wrong_size}",
    )

    # --- claim 5: how much runs -----------------------------------------------------------
    plain, hot, kinds = sizes(patch, defaults)
    check(
        "at the patch's own defaults the pack runs 1907 plain lines and hands the game 2131 hotfixes",
        (plain, hot, kinds) == (1907, 2131, {"everywhere": 1439, "map": 370, "package": 322}),
        f"{plain} plain, {hot} hotfixes {kinds} (measured on Community Patch 5.0.4, 2026-09-24)",
    )

    # BLCMM's own compile of this file is at its end, and it is what a real player's game runs.
    # With the patch's own defaults the pack must hand the game exactly that: the same plain
    # lines, and the same hotfix entries, type and text, in the form the game's service reads.
    tail_plain, tail_hot, n_keys, n_values = blcmm_compile(patch)
    ours_plain, ours_hot, _i = commands_from(patch, None)
    ours_entries = [entry(w, c) for w, c in ours_hot]
    check(
        "at the patch's defaults the pack runs exactly the plain lines BLCMM compiles",
        n_keys == n_values and sorted(ours_plain) == sorted(tail_plain),
        f"{len(ours_plain)} ours, {len(tail_plain)} BLCMM's; only ours "
        f"{sorted(set(ours_plain) - set(tail_plain))[:2]}, only BLCMM's "
        f"{sorted(set(tail_plain) - set(ours_plain))[:2]}",
    )
    check(
        "and hands the game exactly the hotfix entries BLCMM compiles, Gearbox's own aside",
        sorted(ours_entries) == sorted(tail_hot),
        f"{len(ours_entries)} ours, {len(tail_hot)} BLCMM's (of {n_keys}); only ours "
        f"{sorted(set(ours_entries) - set(tail_hot))[:2]}, only BLCMM's "
        f"{sorted(set(tail_hot) - set(ours_entries))[:2]}",
    )
    # This used to compare against a frozen (sent, held) pair, which went stale the moment
    # Lumi ticked or unticked anything in the menu - the number described one day's settings,
    # not a rule. What should always hold, whatever she has ticked, is that every command a
    # chosen section contributes lands somewhere: nothing doubles up between sections and
    # nothing goes missing. EXPECTED_COUNTS (checked against patch.txt itself, above) gives
    # each section's true size through a completely different code path (sections_in, not
    # commands_from) - summing it over on_disk is an independent way to the same total, not
    # the same number typed twice.
    plain_live, hot_live, _kinds_live = sizes(patch, on_disk)
    expected_live = sum(EXPECTED_COUNTS.get(name, 0) for name in on_disk)
    skipped_live = skipped_by_blcmm(patch, on_disk)
    check(
        "the settings saved on this machine run every line of those sections BLCMM would run, none twice",
        plain_live + hot_live + skipped_live == expected_live,
        f"{plain_live} plain + {hot_live} hotfixes + {skipped_live} BLCMM would not run = "
        f"{plain_live + hot_live + skipped_live}; the {len(on_disk)} ticked sections hold "
        f"{expected_live} lines in patch.txt",
    )

    # --- claim 6: the map-gated share -----------------------------------------------------
    _commands, hotfixes, _ignored = commands_from(patch, on_disk)
    by_map = {}
    for level, command in hotfixes:
        if kind(level) == "map":
            by_map.setdefault(level.lower(), []).append(command)
    _ec, extras_hotfixes, _ei = commands_from(extras, extras_sections)
    for level, command in extras_hotfixes:
        if kind(level) == "map":
            by_map.setdefault(level.lower(), []).append(command)
    check(
        "the map-gated commands are spread over eighty maps once case is folded",
        len(by_map) == 80,
        f"{len(by_map)} maps, {sum(len(v) for v in by_map.values())} commands",
    )

    # --- claim 7: the map spelled two ways ------------------------------------------------
    spellings = {'level="BackBurner_P"': patch.count('level="BackBurner_P"'),
                 'level="Backburner_P"': patch.count('level="Backburner_P"')}
    check(
        "patch.txt really does spell the same map BackBurner_P and Backburner_P",
        all(count > 0 for count in spellings.values()),
        f"{spellings}, folding to {len(by_map.get('backburner_p', []))} commands under one key",
    )

    # --- claim 8: a section the patch ships on runs as it ships ---------------------------
    # Until ticket 49's review a ticked section ran whole, flags and all, which ran every option
    # of each choose-one group, the last one winning: Pete's shipped "Explosion" lost to the
    # "No Explosion" the patch ships off. Now not one line a shipped-on section flags off runs.
    shipped_commands, shipped_hotfixes, _si = commands_from(patch, None)
    shipped_on = set(shipped_commands) | {c for _lvl, c in shipped_hotfixes}
    default_commands, default_hotfixes, _di = commands_from(patch, defaults)
    default_all = set(default_commands) | {c for _lvl, c in default_hotfixes}
    extra_fired = sorted(default_all - shipped_on)
    pete = [c for c in default_all if "BodyDeath_Iris_Raid_PyroPete" in c]
    check(
        "a ticked section runs as the patch ships it, so Pete's death explosion stays the shipped one",
        not extra_fired and len(pete) == 3,
        f"{len(extra_fired)} lines flagged off ran: {[c[:90] for c in extra_fired]}; "
        f"{len(pete)} of Pete's 4 lines run",
    )

    # --- claim 9: the extras Lumi ticked are still names the code knows -------------------
    # Extras ship switched off in patch.txt itself - there is no code-side default for them
    # to agree with, so which ones are on is entirely Lumi's call, made in the menu, not
    # something a check gets an opinion on. What the code can promise is that it still
    # recognises every name the settings file mentions; if an extra were ever renamed or
    # removed here, an old settings file still ticking it would silently do nothing, and
    # that silent mismatch is what this now catches instead.
    extras_on = sorted(name for name, _short, _what in EXTRAS if saved.get(name))
    stale_keys = sorted(
        key for key in saved if key not in every_section and key != "Use the Community Patch"
    )
    check(
        "the settings file's Community Patch keys are all names the code still recognises",
        not stale_keys,
        f"{len(extras_on)} extras switched on: {extras_on}; keys the code no longer names:"
        f" {stale_keys}",
    )

    # --- claim 12: the renamed master switch ---------------------------------------------
    check(
        "the settings page no longer holds an option with the same name as the page",
        "Community Patch" not in saved and "Use the Community Patch" in saved,
        f"keys of the Community Patch page include: {sorted(saved)[:3]} ...",
    )
    bad_option = [line for line in log if "is not a valid value for option" in line]
    check(
        "this launch logged no complaint about an option value it could not read",
        not bad_option,
        f"{len(bad_option)} such lines: {bad_option[:2]}",
    )

    # --- claim 11: once per launch --------------------------------------------------------
    applied = [line for line in log if "Community Patch applied" in line]
    check(
        "the log holds exactly one 'Community Patch applied' line for this launch",
        len(applied) == 1,
        f"{len(applied)} lines; last: {applied[-1][80:].strip() if applied else 'none'}",
    )

    # --- claim 4 / the bug behind it ------------------------------------------------------
    # Until ticket 49 this line always said "0 failed", because the pack could not tell a landed
    # command from an ignored one. _run now reads every line back, so the line says how many
    # landed, and landed + failed + not loaded is every command it ran.
    counted = [
        re.search(r"(\d+) commands run, (\d+) failed; read back, (\d+) landed and (\d+) are not loaded", line)
        for line in applied
    ]
    check(
        "that line counts what landed, and its numbers add up to the commands run",
        bool(counted) and counted[-1] is not None
        and int(counted[-1].group(1)) == sum(int(counted[-1].group(n)) for n in (2, 3, 4))
        and int(counted[-1].group(3)) > 0,
        applied[-1].split("INFO|")[-1].strip() if applied else "no line to read",
    )

    # --- claim 6, delivery, as far as the log can show it ---------------------------------
    # The game applies a map's hotfixes when the map loads; the core reads them back on arrival.
    arrived = [
        re.search(r"arrived in (\S+); \d+ hotfixes in effect \(\d+ for every level, (\d+) for this map", line)
        for line in log
    ]
    arrived = [m for m in arrived if m]
    with_map = [m.group(1) for m in arrived if int(m.group(2)) > 0]
    unknown = [name for name in with_map if name not in by_map]
    check(
        "the log shows a map's own hotfixes in effect on arrival somewhere",
        bool(with_map),
        f"{len(arrived)} arrivals logged, {len(with_map)} with the map's own lines: {sorted(set(with_map))}",
    )
    check(
        "every map the log says had its own lines in effect is one the patch really names",
        not unknown,
        f"maps the patch names nothing for: {unknown}",
    )

    # --- the undefended collision between the two patch files -----------------------------
    collisions = sorted(targets(patch, every_section) & targets(extras, extras_sections))
    check(
        "no object and property is written by both the Community Patch and the pack's extras",
        not collisions,
        f"{len(collisions)} collisions (extras register second, so they would win): "
        f"{collisions[:4]}",
    )

    # --- the constants the in-game file hardcodes -----------------------------------------
    hide_commands, hide_hotfixes, _hi = commands_from(patch, {HIDE_DAMAGE})
    hide_paths = {c.split(None, 3)[1] for c in hide_commands + [c for _l, c in hide_hotfixes]}
    check(
        "the four objects community-patch.py hardcodes are still the Hide damage numbers targets",
        hide_paths == DAMAGE_EMITTERS,
        f"{len(hide_paths)} paths; missing {sorted(DAMAGE_EMITTERS - hide_paths)},"
        f" unexpected {sorted(hide_paths - DAMAGE_EMITTERS)}",
    )

    return summary()


if __name__ == "__main__":
    good, total = main()
    sys.exit(0 if good == total else 1)
