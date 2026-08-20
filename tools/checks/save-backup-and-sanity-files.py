# Save backup and Sanity Saver, the half that lives on disk - claims from
# AUDIT-RAW/save-backup.md and AUDIT-RAW/sanity-saver.md
#
# Ordinary Python, outside the game:  python bl2-mcp/tools/checks/save-backup-and-sanity-files.py
#
# READ ONLY. Nothing here writes, renames or deletes a file. It reads the owner's saves, the
# backup folder beside them, Sanity Saver's sidecars and unrealsdk.log.
#
# The log checks describe the launch the log file holds, which is the running session. Run them
# while the game is up; a log rolled by a later launch answers about that launch instead.

import gzip
import importlib.util
import json
import re
from pathlib import Path

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


GAME = Path(__file__).resolve().parents[3]
LOG = GAME / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
SIDECARS = GAME / "sdk_mods" / "SanitySaver" / "Saves"
SETTINGS = GAME / "sdk_mods" / "settings" / "SanitySaver.json"
GENERATION = re.compile(r"^(Save.+\.sav)\.(\d+)$")


def savedata_dir():
    """Ask the pack's own module where the saves are, rather than guessing at Documents."""
    path = GAME / "sdk_mods" / "bl2_modern" / "gamefiles.py"
    spec = importlib.util.spec_from_file_location("sw_gamefiles_readonly", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.savedata_dir()


def check_the_log():
    if not LOG.is_file():
        check("the sdk log is where the checks expect it", False, str(LOG))
        return
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()

    launches = [i for i, l in enumerate(lines) if "pyunrealsdk::init@" in l]
    backed_up = [i for i, l in enumerate(lines) if "savebackup: " in l and " saves, " in l]
    from_the_pack = [i for i, l in enumerate(lines) if "bl2_modern" in l]

    check(
        "the save backup runs exactly once per launch",
        len(backed_up) == len(launches) and len(launches) >= 1,
        f"{len(launches)} launches in this log, {len(backed_up)} backup runs: "
        + "; ".join(lines[i].split("INFO|")[-1].strip() for i in backed_up),
    )
    check(
        "the save backup is the first thing the pack does",
        bool(backed_up) and bool(from_the_pack) and min(backed_up) == min(from_the_pack),
        f"first line from the pack is at index {min(from_the_pack) if from_the_pack else '-'}, "
        f"first backup line at {min(backed_up) if backed_up else '-'}: "
        + (lines[min(from_the_pack)].split("|")[-1].strip() if from_the_pack else ""),
    )

    patched = [i for i, l in enumerate(lines) if "commands run" in l]
    sanity = [i for i, l in enumerate(lines) if "sanitysaver:" in l]
    check(
        "the pack says what it did about Sanity Saver at least once per launch",
        len(sanity) >= len(launches) >= 1,
        f"{len(sanity)} sanitysaver lines for {len(launches)} launches - a launch that never "
        "reaches the main menu produces none, and nothing else distinguishes 'ran and worked' "
        "from 'never ran'",
    )
    check(
        "Sanity Saver is switched on only after the bundled patch has run",
        bool(patched) and bool(sanity) and min(patched) < min(sanity),
        f"first patch line at {min(patched) if patched else '-'}, first sanitysaver line at "
        f"{min(sanity) if sanity else '-'}",
    )

    # A character being live is the first thing that re-applies the level-load hotfixes. If none
    # has been live this session there is nothing to order against, so this is not asked at all
    # rather than passed for free.
    spawned = [i for i, l in enumerate(lines) if "hotfix commands on level load" in l]
    if spawned and sanity:
        check(
            "no character had loaded before Sanity Saver was switched on",
            min(spawned) > min(sanity),
            f"first character live at line {min(spawned)}, Sanity Saver at {min(sanity)}",
        )
    else:
        print("[NOTE] no character has been live this session, so load ordering is not asked")

    if sanity:
        print("[NOTE] " + lines[min(sanity)].split("INFO|")[-1].strip())


def check_the_backups():
    root = savedata_dir()
    if not root.is_dir():
        check("the save folder is where the pack looks for it", False, str(root))
        return

    accounts = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    check(
        "exactly one numbered account folder sits under SaveData",
        len(accounts) == 1,
        f"{[p.name for p in accounts]} - the feature backs nothing up at all unless there is "
        f"exactly one (savebackup.py:62-70), and says so only in the log",
    )
    if len(accounts) != 1:
        return

    account = accounts[0]
    backups = account / "bl2_modern_backups"
    saves = sorted(account.glob("Save*.sav"))
    check(
        "the backup folder exists beside the saves",
        backups.is_dir(),
        str(backups),
    )
    if not backups.is_dir():
        return

    files = [p for p in backups.iterdir() if p.is_file()]
    named = {p.name: GENERATION.match(p.name) for p in files}
    unnamed = sorted(n for n, m in named.items() if m is None)
    check(
        "every file in the backup folder is one numbered generation of a save",
        not unnamed,
        f"{len(files)} files, {unnamed} do not look like Save....sav.N",
    )

    history = {}
    for name, match in named.items():
        if match:
            history.setdefault(match.group(1), set()).add(int(match.group(2)))

    too_deep = {base: sorted(gens) for base, gens in history.items() if max(gens) > 5}
    check(
        "nothing older than the fifth generation survives",
        not too_deep,
        f"{len(history)} saves have backups; deeper than five: {too_deep}",
    )
    gapped = {
        base: sorted(gens) for base, gens in history.items() if gens != set(range(1, max(gens) + 1))
    }
    check(
        "no save's backup history has a hole in it",
        not gapped,
        f"histories with a gap: {gapped}",
    )

    # copy2 carries the save's own timestamp onto the copy, and each generation comes from a
    # different launch, so .1 must be at least as new as .2 and so on. Compared with a second of
    # slack, deliberately: several generations here came from saves the game wrote in one burst
    # milliseconds apart, and their order within that burst says nothing about rotation.
    SLACK_NS = 1_000_000_000
    out_of_order = {}
    for base, gens in history.items():
        stamps = [(backups / f"{base}.{i}").stat().st_mtime_ns for i in sorted(gens)]
        if any(newer + SLACK_NS < older for newer, older in zip(stamps, stamps[1:])):
            out_of_order[base] = [
                (backups / f"{base}.{i}").stat().st_mtime for i in sorted(gens)
            ]
    check(
        "each save's .1 is its newest copy and .5 its oldest",
        not out_of_order,
        f"{len(history)} histories checked, out of order by more than a second: {out_of_order}",
    )

    live = {p.name for p in saves}
    have_one = {name for name, gens in history.items() if 1 in gens}
    check(
        "every save in the account folder has a backup",
        live <= have_one,
        f"{len(live)} saves, missing a backup: {sorted(live - have_one)}",
    )

    # copy2 keeps the save's timestamp, so a backup whose timestamp still matches its save has
    # not been overtaken by a later save and must hold exactly those bytes. Saves the game has
    # written since the last launch cannot be compared this way and are counted, not guessed at.
    comparable = [
        save
        for save in saves
        if (backups / f"{save.name}.1").is_file()
        and (backups / f"{save.name}.1").stat().st_mtime_ns == save.stat().st_mtime_ns
    ]
    different = [
        save.name
        for save in comparable
        if (backups / f"{save.name}.1").read_bytes() != save.read_bytes()
    ]
    if comparable:
        check(
            "a backup whose timestamp still matches its save holds exactly that save's bytes",
            not different,
            f"{len(comparable)} of {len(saves)} saves untouched since their backup, "
            f"{len(different)} of those differ: {different}",
        )
    else:
        # Every save on disk has a newer mtime than its own .1 backup right now - the game has
        # written to all of them since the last backup ran, which just means it has been played
        # since. There is nothing byte-identical left to compare against, so this is an
        # environment gap, not a defect: printing FAIL here would blame the feature for saves
        # that simply moved on since their last backup.
        print(
            "[SKIP] a backup whose timestamp still matches its save holds exactly that save's "
            f"bytes   0 of {len(saves)} saves are comparable right now - every save has been "
            "written to since its last backup, so nothing can be proven either way this run",
        )

    total_mb = sum(p.stat().st_size for p in files) / (1024 * 1024)
    orphans = sorted(base for base in history if base not in live)
    check(
        "the backup folder is under the 500 MB mark the feature warns at",
        total_mb < 500,
        f"{total_mb:.1f} MB in {len(files)} files, of which {len(orphans)} sets belong to saves "
        f"that no longer exist ({orphans}) - nothing ever removes those",
    )

    # save-backup.md, suspected bugs: the .sav is only half of a character once Sanity Saver is
    # in play. Its sidecar holds the parts of every item the game cannot serialise, and lives in
    # sdk_mods/SanitySaver/Saves. savebackup.py copies it into a "SanitySaver" subfolder of its
    # own under bl2_modern_backups - this check used to look for it with a plain iterdir() over
    # backups itself, one level too shallow, so it reported every sidecar as uncopied even when
    # the subfolder held it. MEASURED 2026-08-20: the real backup folder already holds
    # bl2_modern_backups/SanitySaver/Save0108.json.gz.1 (and the same for every other sidecar in
    # SIDECARS) - the feature was never the problem, this check was looking in the wrong place.
    sidecar_backups = backups / "SanitySaver"
    sidecar_backup_names = (
        [p.name for p in sidecar_backups.iterdir()] if sidecar_backups.is_dir() else []
    )
    with_sidecar = [s for s in saves if (SIDECARS / (s.stem + ".json.gz")).is_file()]
    unprotected = [
        s.name
        for s in with_sidecar
        if not any(name.startswith(s.stem + ".json") for name in sidecar_backup_names)
    ]
    check(
        "each backed-up save has its Sanity Saver sidecar backed up too",
        not unprotected,
        f"{len(with_sidecar)} saves carry a sidecar in {SIDECARS}; not copied to "
        f"{sidecar_backups}: {unprotected}. Restoring a .sav generation pairs an old save with "
        "today's item parts",
    )


def check_sanity_saver_files():
    check(
        "Sanity Saver's settings file exists",
        SETTINGS.is_file(),
        str(SETTINGS),
    )
    if SETTINGS.is_file():
        settings = json.loads(SETTINGS.read_text(encoding="utf-8", errors="replace"))
        check(
            "Sanity Saver's own settings say it is enabled, so it comes back on next launch",
            settings.get("enabled") is True,
            f"enabled={settings.get('enabled')!r} in {SETTINGS.name}",
        )

    if not SIDECARS.is_dir():
        check("Sanity Saver has a folder to keep item parts in", False, str(SIDECARS))
        return

    sidecars = sorted(SIDECARS.glob("*.json.gz"))
    broken = []
    wrong_version = []
    for path in sidecars:
        try:
            data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        except Exception as ex:  # noqa: BLE001
            broken.append(f"{path.name}: {ex!r}")
            continue
        if data.get("save_version") != 2:
            wrong_version.append(f"{path.name}: {data.get('save_version')!r}")

    check(
        "every item-parts sidecar is readable",
        not broken,
        f"{len(sidecars)} sidecars, unreadable: {broken}",
    )
    check(
        "every item-parts sidecar is at the save version this copy of Sanity Saver writes",
        not wrong_version,
        f"expected save_version 2 (save_manager.py:14), off: {wrong_version}",
    )

    # sanity-saver.md, suspected bugs: SaveManager builds its filename from
    # Path(save_name).stem, so a SaveManager built with an empty name writes to a file called
    # ".json.gz". One exists, which means at least one round-trip stored a character's item
    # parts under no character's name.
    anonymous = SIDECARS / ".json.gz"
    contents = ""
    if anonymous.is_file():
        try:
            data = json.loads(gzip.decompress(anonymous.read_bytes()).decode("utf-8"))
            contents = f" holding {len(data.get('items', {}))} items: " + ", ".join(
                str(v.get("_description")) for v in list(data.get("items", {}).values())[:4]
            )
        except Exception as ex:  # noqa: BLE001
            contents = f" (unreadable: {ex!r})"
    check(
        "no item parts were saved under an empty save name",
        not anonymous.is_file(),
        f"{anonymous}{contents}",
    )


if __name__ == "__main__":
    print(f"game folder: {GAME}")
    check_the_log()
    check_the_backups()
    check_sanity_saver_files()
    summary()
