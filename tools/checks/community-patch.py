# Community Patch - checks for the claims in AUDIT-RAW/community-patch.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/community-patch.py
#
# Nothing here waits for anything. The one claim that genuinely needs a map change - that the
# map-gated commands are DELIVERED on arrival rather than merely held - is in
# community-patch-needs-travel.py. Claims about patch.txt, the settings file and the log are in
# community-patch-files.py, which runs outside the game.
#
# Two ways this file avoids firing thousands of console commands at a live game:
#   - the wiring checks swap core._run for a recorder, so _run_one_patch does all its real work
#     (read the file, parse it, honour the switches, sort the hotfixes) and sends nothing;
#   - the "do commands land" check writes to at most ~116 numeric properties and puts every one
#     of them back, by hand, in the finally.
reset()

import pathlib

import unrealsdk

from bl2_modern import core
from bl2_modern.features import communitypatch as cp
from bl2_modern.patchfile import commands_from, sections_in
from bl2_modern.patchsections import EXTRAS, NOT_A_SWITCH, SECTIONS, all_names

PATCH = pathlib.Path(core.__file__).parent / "data" / "patch.txt"
SENTINEL = "123456"

# The four objects of the "Hide Damage Numbers/Critical/Resist" extra, copied out of patch.txt on
# 2026-08-19. community-patch-files.py asserts those four lines are still the ones in the file, so
# this list going stale is caught rather than quietly passing.
DAMAGE_EMITTERS = [
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_0",
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_1",
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_3",
    "FX_CHAR_Damage_Matrix.Particles.Part_Dynamic_Number:ParticleSpriteEmitter_17",
]
HIDE_DAMAGE = "Hide Damage Numbers/Critical/Resist"

controller = pc()
text = PATCH.read_text(encoding="utf-8", errors="replace")  # 4.6 MB, measured at ~30 ms to parse

# Everything the live launch produced, snapshotted before this script touches a thing.
live_by_level = {name: list(held) for name, held in core._by_level.items()}
live_levels = {name: len(held) for name, held in live_by_level.items()}
live_repeat = list(core._repeat_on_level_load)
live_wanted = cp.wanted_sections()

# --- what has to be put back ---------------------------------------------------------------
real_run = core._run
sent = []
saved_master = cp.enabled.value
all_switches = dict(cp._section_options)
all_switches.update(cp._extra_options)
saved_switches = {name: option.value for name, option in all_switches.items()}
touched = []  # (path, property, the value it had before this script wrote to it)


def recording_run(commands):
    """Stands in for core._run: counts what would have been sent, sends nothing."""
    sent.extend(commands)
    return len(commands), 0, 0


def probe(sections):
    """Run one patch through the core exactly as the pack does, with the console unplugged."""
    sent.clear()
    core._by_level.clear()
    core._repeat_on_level_load[:] = []
    core._run_one_patch(core.Feature(name="probe", patch_sections=lambda: sections))
    return list(sent), {name: len(held) for name, held in core._by_level.items()}


try:
    # --- the switches themselves ----------------------------------------------------------
    found = sections_in(text)
    dead = [name for name in all_names() if name not in found]
    check(
        "every switch in the menu points at a section that really exists in the shipped patch",
        not dead,
        f"{len(all_names())} switches, {len(found)} sections in the file; dead: {dead}",
    )
    unlisted = sorted(set(found) - set(all_names()) - NOT_A_SWITCH)
    check(
        "the shipped patch has no section that the menu cannot reach",
        not unlisted,
        f"unreachable: {unlisted}",
    )

    declared_on = [
        name for name, _short, _what in EXTRAS if cp._extra_options[name].default_value
    ]
    check(
        "all eleven optional extras are declared switched off in the code",
        len(EXTRAS) == 11 and not declared_on,
        f"{len(EXTRAS)} extras; declared on: {declared_on}",
    )
    declared_off = [
        name for name, _short, on, _what in SECTIONS
        if not on or not cp._section_options[name].default_value
    ]
    check(
        "all eight ordinary sections are declared switched on in the code",
        len(SECTIONS) == 8 and not declared_off,
        f"{len(SECTIONS)} sections; declared off: {declared_off}",
    )
    # A REPORT, not a check, and the difference matters. These eleven are the extras the patch
    # authors ship switched off; the pack exposes each as its own row precisely so somebody can
    # tick the ones they want. Ticking them is the feature working, so failing the run over it
    # was calling somebody's own choice a defect, every single time, forever.
    #
    # What is worth catching is a stray toggle nobody meant, and only the person playing can
    # tell those apart - so this prints the list and leaves the judging to them.
    drifted = [
        name for name, _short, _what in EXTRAS
        if cp._extra_options[name].value != cp._extra_options[name].default_value
    ]
    print(f"   ({len(drifted)} of the {len(EXTRAS)} optional extras are ticked on this machine, "
          f"against the patch authors' own defaults: {drifted})")
    check(
        "every optional extra has a switch of its own, so none of them is on by accident",
        all(name in cp._extra_options for name, _s, _w in EXTRAS),
        f"{[n for n, _s, _w in EXTRAS if n not in cp._extra_options]} have no switch",
    )

    check(
        "the master switch is saved under a different name from the settings page it sits in",
        cp.enabled.identifier == "Use the Community Patch",
        f"identifier is {cp.enabled.identifier!r}; the page it lives in is named 'Community Patch'",
    )

    # --- what the switches say to run -----------------------------------------------------
    cp.enabled.value = False
    master_off = cp.wanted_sections()
    cp.enabled.value = True
    master_on = cp.wanted_sections()
    cp.enabled.value = saved_master
    check(
        "switching the Community Patch off means skip it entirely, not run zero sections",
        master_off is None,
        f"wanted_sections() returned {master_off!r}",
    )
    # Not "is it a set" - the failure worth catching is wanted_sections consulting only
    # _section_options and quietly dropping every optional extra the player ticked.
    ticked = {name for name, option in all_switches.items() if option.value}
    check(
        "switching it back on names every section and every extra the player has ticked",
        master_on == ticked,
        f"{len(master_on or ())} named, {len(ticked)} ticked;"
        f" missing {sorted(ticked - (master_on or set()))}",
    )

    # --- the map-gated table the real launch built ----------------------------------------
    # A floor, not an exact number: adding a text mod that gates commands on more maps is a
    # normal thing to do, and the check should not fail for it. Dropping below the Community
    # Patch's own 80 would mean the core stopped holding things, which is worth catching.
    check(
        "the patch is holding commands for at least the eighty maps the Community Patch names",
        len(live_levels) >= 80,
        f"{len(live_levels)} maps held",
    )
    # DERIVED, not written down. This used to assert 483 - the number the two patch files held
    # on the day it was written - and it went stale the moment a section was added to extras.txt.
    # Working the number out from the files themselves means the check still fails if the core
    # DROPS something, which is the thing worth catching, and stops failing for the pack growing.
    import pathlib as _pathlib

    from bl2_modern.patchfile import commands_from as _commands_from

    _data = _pathlib.Path(core.__file__).parent / "data"
    _expected = 0
    for _feature in core.all_features():
        if _feature.failed is not None or _feature.patch_sections is None:
            continue
        _wanted = _feature.patch_sections()
        _path = _data / _feature.patch_file
        if _wanted is None or not _path.is_file():
            continue
        _, _hot, _ = _commands_from(
            _path.read_text(encoding="utf-8", errors="replace"), _wanted,
        )
        _expected += len([1 for _lvl, _c in _hot if _lvl not in ("None", "")])
    check(
        "every command the patch files gate on a map is being held for that map, and no others",
        sum(live_levels.values()) == _expected,
        f"{sum(live_levels.values())} held, {_expected} gated across "
        f"{len(live_levels)} maps in the files the pack is actually running",
    )
    mixed_case = [name for name in live_levels if name != name.lower()]
    check(
        "every map the patch is filed under is stored in lower case",
        not mixed_case,
        f"stored with capitals: {mixed_case}",
    )
    # The patch spells this map two ways. Five commands land under one key only because the core
    # lower-cases; a case-sensitive dict would give two keys and the watcher would match at most
    # one of them. community-patch-files.py checks both spellings really are in the file.
    # The audit says this key holds 4 commands. Measured 2026-08-19 against the shipped file: 5.
    # At least five: the Community Patch spells the map two ways and the core lower-cases both,
    # so all of them land under one key. Another text mod naming the same map adds more, which
    # is not a failure - what would be is fewer than the Community Patch alone puts there.
    check(
        "both spellings of BackBurner_P end up filed under the one lower-case name",
        (live_levels.get("backburner_p") or 0) >= 5,
        f"backburner_p holds {live_levels.get('backburner_p')} commands",
    )

    here = core._current_map(controller)
    check(
        "the map watcher has already matched the map you are standing in",
        here is not None and core._map_done == here,
        f"_map_done={core._map_done!r}, the map reads as {here!r}, where() says {where()!r}",
    )
    # This one PASSES because the bug is present, and it is written that way on purpose: if the
    # diagnostic is ever fixed to speak once per map, this check turns red and that is the good
    # news. _logged_map_name latches on the first sample of the session, which the log shows is
    # 'menumap' - so the one line guarding 483 map-gated commands reports on the main menu.
    check(
        "the once-per-launch map-name diagnostic is spent and can never report on a real map",
        core._logged_map_name is True,
        f"_logged_map_name={core._logged_map_name}, and you are in {here!r}",
    )

    # --- claim 13, the half of it that is not "does it look right on screen" ---------------
    states = []
    for path in DAMAGE_EMITTERS:
        try:
            states.append(len(unrealsdk.find_object("Object", path).LODLevels))
        except Exception as ex:  # noqa: BLE001 - an unloaded object is a real answer here
            states.append(repr(ex))
    readable = [state for state in states if isinstance(state, int)]
    check(
        "all four damage-number emitters can be read at all",
        len(readable) == 4,
        f"LODLevels lengths: {states}",
    )
    hiding = HIDE_DAMAGE in (live_wanted or set())
    emptied = [state for state in readable if state == 0]
    check(
        "the damage-number emitters agree with the Hide damage numbers switch",
        (len(emptied) == 4) if hiding else (len(readable) == 4 and not emptied),
        f"switch is {'ON' if hiding else 'off'}; {len(emptied)} of {len(readable)} emitters emptied",
    )

    # --- feature -> core -> parser, with the console unplugged ----------------------------
    core._run = recording_run

    cp.enabled.value = False
    off_sent, off_levels = probe(cp.wanted_sections())
    cp.enabled.value = saved_master
    check(
        "with the master switch off the pack sends no commands at all",
        not off_sent,
        f"{len(off_sent)} commands sent",
    )
    check(
        "with the master switch off nothing is held back for any map either",
        not off_levels,
        f"{sum(off_levels.values())} commands held for {len(off_levels)} maps",
    )

    ticked_sent, _ = probe(cp.wanted_sections())
    probe_repeat = list(core._repeat_on_level_load)
    cp._section_options["Cosmetic Changes"].value = False
    fewer_sent, _ = probe(cp.wanted_sections())
    cp._section_options["Cosmetic Changes"].value = saved_switches["Cosmetic Changes"]
    check(
        "unticking Reskins removes exactly its 1119 commands from what gets sent",
        len(ticked_sent) - len(fewer_sent) == 1119,
        f"{len(ticked_sent)} sent with it on, {len(fewer_sent)} with it off",
    )
    check(
        "an unticked section takes nothing else with it",
        len(fewer_sent) > 0 and set(fewer_sent) < set(ticked_sent),
        f"{len(set(ticked_sent) - set(fewer_sent))} commands dropped, {len(fewer_sent)} kept",
    )
    # The pack asks the switches at the moment it runs, not at import - so what it actually put on
    # the level-load list at the main menu must still be what today's switches ask for. The
    # Community Patch registers before Extras, so its share is the front of the live list.
    check(
        "the commands the pack repeats on every level load are the ones today's switches ask for",
        len(probe_repeat) > 0 and live_repeat[: len(probe_repeat)] == probe_repeat,
        f"the launch put {len(live_repeat)} commands on the level-load list; today's switches want"
        f" {len(probe_repeat)} of them from the Community Patch",
    )

    sent.clear()
    core.run_bundled_patch()
    check(
        "asking the pack to apply the patch a second time does nothing",
        not sent,
        f"{len(sent)} commands sent on a second call to run_bundled_patch()",
    )
    check(
        "the pack has recorded that both the patch and the main menu already happened",
        core._patch_has_run and core._main_menu_done,
        f"_patch_has_run={core._patch_has_run}, _main_menu_done={core._main_menu_done}",
    )

    core._run = real_run

    # --- claim 4: the log line counts effects, not calls ------------------------------------
    # Until ticket 49 this passed with (1 run, 0 failed): ConsoleCommand does not raise on a set
    # naming an object that does not exist, so _run counted it as run. _run now reads every line
    # back, so the same line is counted as waiting for its object, and never as landed.
    landed, failed, absent = core._run(["set No.Such.Object NoSuchProp 1"])
    check(
        "a set naming an object that does not exist is counted as not loaded, not as landed",
        (landed, failed, absent) == (0, 0, 1),
        f"_run reported {landed} landed, {failed} failed, {absent} not loaded",
    )

    # --- claim 3: do the patch's commands actually change anything ------------------------
    # Sentinel sandwich: write 123456, confirm the property moved (a target that does not move
    # proves nothing either way), then run the patch's own line and confirm it moved back. Only
    # properties whose name is a plain identifier and whose current value is a bare number are
    # touched, because those are the only ones that can be written back exactly afterwards.
    commands, hotfixes, _ignored = commands_from(text, live_wanted)
    pool = []
    for command in commands + [c for lvl, c in hotfixes if lvl in ("None", "")]:
        parts = command.split(None, 3)
        if len(parts) != 4 or parts[0].lower() != "set":
            continue
        _set, path, prop, want = parts
        want = want.strip()
        if not prop.isidentifier():
            continue
        try:
            float(want)
        except ValueError:
            continue
        pool.append((path, prop, want))

    usable = landed = inert = unresolved = errored = 0
    misses = []
    for path, prop, want in pool:
        try:
            obj = unrealsdk.find_object("Object", path)
            before = str(getattr(obj, prop))
        except Exception:  # noqa: BLE001 - an unloaded object is one of the answers
            unresolved += 1
            continue
        try:
            float(before)
        except ValueError:
            continue
        try:
            touched.append((path, prop, before))
            controller.ConsoleCommand(f"set {path} {prop} {SENTINEL}")
            mid = str(getattr(obj, prop))
            if mid == before:
                continue  # the sentinel never landed, so this target can say nothing
            usable += 1
            controller.ConsoleCommand(f"set {path} {prop} {want}")
            after = str(getattr(obj, prop))
            if after == mid:
                inert += 1
                if len(misses) < 8:
                    misses.append((path, prop, before, after))
            else:
                landed += 1
        except Exception as ex:  # noqa: BLE001 - keep going, and say so
            errored += 1
            if len(misses) < 8:
                misses.append((path, prop, "raised", repr(ex)))

    check(
        "enough of the patch's targets are loaded for this to mean anything",
        usable >= 20,
        f"{usable} usable of {len(pool)} numeric targets"
        f" ({unresolved} objects not loaded, {errored} raised)",
    )
    check(
        "the patch's own set commands really do change the objects they name",
        usable > 0 and inert == 0,
        f"{landed} landed, {inert} did nothing; first misses: {misses}",
    )
    # A REPORT, because "loaded right now" is a fact about where you are standing, not about the
    # patch. Borderlands 2 loads a package when something needs it: a map's objects arrive with
    # the map, a character's skill tree arrives with that character. So a patch line naming
    # Krieg's Mania tree cannot resolve while you are playing Zer0 in Three Horns, and nothing
    # the pack does will change that - the line lands on the machine where somebody is playing
    # Krieg, because the patch runs when a character comes alive.
    #
    # This used to fail the run every single time, which trained anybody reading the results to
    # skip it. The number is still worth seeing, so it is printed.
    print(f"   ({unresolved} of {len(pool)} numeric targets are in packages this map and this "
          f"character have not loaded - they land where they belong, not here)")
    check(
        "the targets that ARE loaded were all reachable, so the reading itself works",
        errored == 0,
        f"{errored} of {len(pool)} raised while being read, which is a different thing from "
        f"not being loaded",
    )

finally:
    core._run = real_run
    cp.enabled.value = saved_master
    for name, value in saved_switches.items():
        all_switches[name].value = value
    core._by_level.clear()
    core._by_level.update({name: list(held) for name, held in live_by_level.items()})
    core._repeat_on_level_load[:] = live_repeat
    for path, prop, original in touched:
        try:
            controller.ConsoleCommand(f"set {path} {prop} {original}")
        except Exception as ex:  # noqa: BLE001 - keep restoring the rest
            print(f"   could not restore {path} {prop} to {original}: {ex!r}")

summary()
