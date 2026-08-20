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
import sys

GAME = pathlib.Path(r"D:/SteamLibrary/steamapps/common/Borderlands 2")
MOD = GAME / "sdk_mods" / "bl2_modern"
SETTINGS = GAME / "sdk_mods" / "settings" / "bl2_modern.json"
LOG = GAME / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"

sys.path.insert(0, str(MOD))

from patchfile import commands_from, sections_in  # noqa: E402
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


def sizes(text, wanted):
    """(sent at the main menu, held for particular maps) for one set of sections."""
    commands, hotfixes, _ignored = commands_from(text, wanted)
    everywhere = [c for lvl, c in hotfixes if lvl in ("None", "")]
    held = [c for lvl, c in hotfixes if lvl not in ("None", "")]
    return len(commands) + len(everywhere), len(held)


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
    sent, held = sizes(patch, defaults)
    check(
        "at the documented defaults the patch sends 3669 commands and holds 370 for maps",
        (sent, held) == (3669, 370),
        f"{sent} sent, {held} held",
    )
    # This used to compare against a frozen (sent, held) pair, which went stale the moment
    # Lumi ticked or unticked anything in the menu - the number described one day's settings,
    # not a rule. What should always hold, whatever she has ticked, is that every command a
    # chosen section contributes lands somewhere: nothing doubles up between sections and
    # nothing goes missing. EXPECTED_COUNTS (checked against patch.txt itself, above) gives
    # each section's true size through a completely different code path (sections_in, not
    # commands_from) - summing it over on_disk is an independent way to the same total, not
    # the same number typed twice.
    sent_live, held_live = sizes(patch, on_disk)
    expected_live = sum(EXPECTED_COUNTS.get(name, 0) for name in on_disk)
    check(
        "the settings saved on this machine send exactly as many commands as those sections hold",
        sent_live + held_live == expected_live,
        f"{sent_live} sent, {held_live} held ({sent_live + held_live} total) from"
        f" {len(on_disk)} ticked sections; those sections hold {expected_live} commands in"
        " patch.txt",
    )

    # --- claim 6: the map-gated share -----------------------------------------------------
    _commands, hotfixes, _ignored = commands_from(patch, on_disk)
    by_map = {}
    for level, command in hotfixes:
        if level not in ("None", ""):
            by_map.setdefault(level.lower(), []).append(command)
    _ec, extras_hotfixes, _ei = commands_from(extras, extras_sections)
    for level, command in extras_hotfixes:
        if level not in ("None", ""):
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

    # --- claim 8: sections run whole, flags and all ---------------------------------------
    # The audit's own assertion here is wrong. It says to count commands mentioning
    # BodyDeath_Iris_Raid_PyroPete inside Fixes and expect 1; there are 4 of them, three of which
    # the patch ships switched on. The real claim is about the ONE command in the default-on set
    # that the patch authors flagged off, so that is what this counts.
    shipped_commands, shipped_hotfixes, _si = commands_from(patch, None)
    shipped_on = set(shipped_commands) | {c for _lvl, c in shipped_hotfixes}
    default_commands, default_hotfixes, _di = commands_from(patch, defaults)
    default_all = set(default_commands) | {c for _lvl, c in default_hotfixes}
    extra_fired = sorted(default_all - shipped_on)
    check(
        "ticking a section runs it whole, and that pulls in exactly one command the patch"
        " authors had switched off",
        len(extra_fired) == 1 and "BodyDeath_Iris_Raid_PyroPete" in extra_fired[0],
        f"{len(extra_fired)} such commands: {[c[:90] for c in extra_fired]}",
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
    # PASSES while the bug is present: the pack cannot tell a landed command from an ignored one,
    # so it reports zero failures out of thousands. If this ever goes red, _run learned to check.
    check(
        "that line claims zero failures, which is what it would say if nothing had landed",
        bool(applied) and "0 failed" in applied[-1],
        applied[-1].split("INFO|")[-1].strip() if applied else "no line to read",
    )

    # --- claim 6, delivery, as far as the log can show it ---------------------------------
    delivered = [line for line in log if "commands for " in line and "applied" in line]
    named = [line.split("commands for ")[1].split(" applied")[0] for line in delivered]
    unknown = [name for name in named if name not in by_map]
    check(
        "the log shows map-gated commands actually being applied on arrival somewhere",
        bool(delivered),
        f"{len(delivered)} arrivals logged: {sorted(set(named))}",
    )
    check(
        "every map the log says it patched is one the patch really holds commands for",
        not unknown,
        f"maps with no held commands: {unknown}",
    )

    # --- the map-name diagnostic bug ------------------------------------------------------
    # Expected to PASS while the bug is present: one line, and it reports on the menu map.
    diagnostic = [line for line in log if "the game calls this map" in line]
    check(
        "the map-name diagnostic speaks once per launch and it speaks about the menu",
        len(diagnostic) == 1 and "menumap" in diagnostic[0] and "has nothing for it" in diagnostic[0],
        f"{len(diagnostic)} lines: {[d.split('INFO|')[-1].strip() for d in diagnostic]}",
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
