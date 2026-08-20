"""
Game feel + the ini editor, the half that lives on disk.

Checks for AUDIT-RAW/game-feel-configtweaks.md and AUDIT-RAW/game-files-ini-editor.md.

    python bl2-mcp/tools/checks/game-feel-and-files-files.py

Ordinary Python - no game, no unrealsdk, no harness. It reads the owner's real config files
and never writes to them: every writer test runs against a throwaway directory with
gamefiles.config_dir monkeypatched at it, which works because edit_ini looks the directory up
through the module global at call time (gamefiles.py:113). The audit says that seam does not
exist and a source change is needed for it; it does exist.
"""

import filecmp
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

GAME = pathlib.Path(__file__).resolve().parents[3]
GAMEFILES_PY = GAME / "sdk_mods" / "bl2_modern" / "gamefiles.py"
SETTINGS_JSON = GAME / "sdk_mods" / "settings" / "bl2_modern.json"
SDK_LOG = GAME / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"

# Every key the pack writes into an ini, from the only two callers of edit_ini
# (configtweaks.py:137,:166 and coopfixes.py:39,:45,:64 - grepped, not recalled).
PACK_KEYS = {
    "benablemousesmoothing",
    "blandingshake",
    "physxlevel",
    "poolsize",
    "badmincanpause",
    "bbossesregenhealthonreset",
    "benemiesforgetdownedplayers",
    "bresurrectallplayerswhenonedies",
}

RESULTS: list = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append({"name": name, "ok": ok, "detail": str(detail)})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


def summary():
    good = sum(1 for r in RESULTS if r["ok"])
    print(f"\n{good}/{len(RESULTS)} passed")
    for r in RESULTS:
        if not r["ok"]:
            print(f"   FAILED: {r['name']}  {r['detail']}")
    return good, len(RESULTS)


def load_gamefiles():
    """Import gamefiles.py on its own, without dragging in the rest of the pack."""
    spec = importlib.util.spec_from_file_location("bl2_gamefiles_under_test", GAMEFILES_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sections(path):
    """Every (section, key, value, line number) in an ini, in order."""
    out = []
    current = None
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped
        elif "=" in stripped and not stripped.startswith(";"):
            key, value = stripped.split("=", 1)
            out.append((current, key.strip(), value.strip(), number))
    return out


def value_in(path, section, key):
    """The first value of one key inside one named section, or None."""
    for found_section, found_key, value, _n in sections(path):
        if found_section == section and found_key.lower() == key.lower():
            return value
    return None


def occurrences(path, key):
    """Every place a key name appears, whatever section it is in."""
    return [(s, v, n) for s, k, v, n in sections(path) if k.lower() == key.lower()]


# --- the real files ------------------------------------------------------------------------


def check_the_real_config(gf):
    config = gf.config_dir()

    check(
        "the ini editor's own self-check still passes",
        _self_check_passes(),
        f"python {GAMEFILES_PY.name}",
    )
    check(
        "Windows hands back a Documents folder that really holds the game's config files",
        config.is_dir() and (config / "WillowEngine.ini").is_file(),
        f"config_dir() = {config}",
    )
    check(
        "the save folder the pack backs up from is there too",
        gf.savedata_dir().is_dir(),
        f"savedata_dir() = {gf.savedata_dir()}",
    )

    # Claim 1 / claim 2: the two booleans, in the right section.
    smoothing = config / "WillowInput.ini"
    check(
        "mouse smoothing is off under [Engine.PlayerInput] in WillowInput.ini",
        value_in(smoothing, "[Engine.PlayerInput]", "bEnableMouseSmoothing") == "False",
        f"bEnableMouseSmoothing={value_in(smoothing, '[Engine.PlayerInput]', 'bEnableMouseSmoothing')!r}",
    )
    found = occurrences(smoothing, "bEnableMouseSmoothing")
    check(
        "mouse smoothing appears exactly once in WillowInput.ini, so there is no second copy "
        "quietly overriding it",
        len(found) == 1,
        f"{found}",
    )

    game_ini = config / "WillowGame.ini"
    check(
        "landing shake is off under [WillowGame.WillowPlayerController] in WillowGame.ini",
        value_in(game_ini, "[WillowGame.WillowPlayerController]", "bLandingShake") == "False",
        f"bLandingShake="
        f"{value_in(game_ini, '[WillowGame.WillowPlayerController]', 'bLandingShake')!r}",
    )

    # Claim 8: PhysXLevel, once, in [SystemSettings].
    engine_ini = config / "WillowEngine.ini"
    physx = occurrences(engine_ini, "PhysXLevel")
    check(
        "PhysXLevel is set to 0 under [SystemSettings] in WillowEngine.ini and appears nowhere else",
        len(physx) == 1 and physx[0][0] == "[SystemSettings]" and physx[0][1] == "0",
        f"{physx}",
    )

    # Claim 9: two PoolSize keys, only one of them ours.
    pools = occurrences(engine_ini, "PoolSize")
    backup = engine_ini.with_suffix(engine_ini.suffix + gf.ORIGINAL_SUFFIX)
    check(
        "WillowEngine.ini really does hold PoolSize more than once, which is the whole reason "
        "edits are scoped to a section",
        len(pools) >= 2,
        f"{pools}",
    )
    if backup.is_file():
        live_texture = value_in(engine_ini, "[TextureStreaming]", "PoolSize")
        live_audio = value_in(engine_ini, "[Wwise.ComponentPool]", "PoolSize")
        was_texture = value_in(backup, "[TextureStreaming]", "PoolSize")
        was_audio = value_in(backup, "[Wwise.ComponentPool]", "PoolSize")
        # The pack does NOT move this one, and that is the point: "Keep the texture buffer at
        # its stock size" ships OFF, meaning leave the owner's own number alone. This used to
        # demand that the pack had changed it, from back when the switch shipped on. The switch
        # went off after measuring that the texture pack, not the buffer, was the memory problem.
        check(
            "the texture streaming PoolSize is the owner's own, untouched by the pack",
            live_texture == was_texture,
            f"[TextureStreaming] PoolSize {was_texture} -> {live_texture}; the switch that would "
            f"move it ships off",
        )
        check(
            "the sound system's PoolSize was left exactly where it was",
            live_audio == was_audio and live_audio is not None,
            f"[Wwise.ComponentPool] PoolSize {was_audio} -> {live_audio}",
        )


def _self_check_passes():
    done = subprocess.run(
        [sys.executable, str(GAMEFILES_PY)],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode == 0 and "gamefiles: all checks passed" in done.stdout


# --- the texture buffer, where a corrected default did not take ---------------------------


def check_texture_buffer(gf):
    engine_ini = gf.config_dir() / "WillowEngine.ini"
    saved = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    switch = saved.get("options", {}).get("Game feel", {}).get(
        "Keep the texture buffer at its stock size",
    )
    # configtweaks.py:95-97 ships this BoolOption defaulted to False, with a comment at :90-94
    # explaining the default was corrected downward so the owner's 512 would survive.
    check(
        "the saved settings agree with the OFF that configtweaks.py:96 ships as the default",
        switch is False,
        f"sdk_mods/settings/bl2_modern.json records {switch!r} - changing a default does not "
        f"migrate an already-saved settings file, the stored value wins",
    )
    check(
        "the texture pool is still the 512 the owner chose, as the default-OFF was meant to ensure",
        value_in(engine_ini, "[TextureStreaming]", "PoolSize") == "512",
        f"[TextureStreaming] PoolSize="
        f"{value_in(engine_ini, '[TextureStreaming]', 'PoolSize')!r}",
    )


# --- the backups, and what restoring one would really do ----------------------------------


def check_backups(gf):
    """
    The pristine copies, judged against what the pack ACTUALLY writes right now.
    
    REWRITTEN 2026-08-20. This used to hold a fixed list of four keys and demand that the copy
    differ from the live file for every one of them. Two of those four are not written at all
    today - "Keep the texture buffer at its stock size" ships off, and PhysXLevel is already the
    0 the game ships - so the demand could not be met however well the copies were kept, and it
    failed every run for the pack correctly leaving something alone.
    
    What has to be true is narrower and actually checkable: for every key the pack IS writing, the
    copy must hold something else, or restoring it undoes nothing.
    """
    config = gf.config_dir()
    saved = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    feel = saved.get("options", {}).get("Game feel", {})

    # (file, section, key, whether the pack is writing it on this machine right now)
    ours = [
        ("WillowInput.ini", "[Engine.PlayerInput]", "bEnableMouseSmoothing",
         feel.get("Turn off mouse smoothing") is True),
        ("WillowGame.ini", "[WillowGame.WillowPlayerController]", "bLandingShake",
         feel.get("Turn off landing camera shake") is True),
        # PhysXLevel is written when the switch is on, but the value written is the same 0 the
        # game ships - so there is nothing for a copy to differ about either way.
        ("WillowEngine.ini", "[SystemSettings]", "PhysXLevel", False),
        ("WillowEngine.ini", "[TextureStreaming]", "PoolSize",
         feel.get("Keep the texture buffer at its stock size") is True),
    ]
    writing = set()
    for filename, section, key, active in ours:
        live = config / filename
        backup = live.with_suffix(live.suffix + gf.ORIGINAL_SUFFIX)
        if not backup.is_file():
            check(f"there is a pristine copy of {filename} to restore from", False, f"{backup}")
            continue
        now, before = value_in(live, section, key), value_in(backup, section, key)
        if not active:
            print(f"   ({key} in {filename} is not being written by the pack right now, so the "
                  f"copy holding the same {before!r} is correct)")
            continue
        writing.add(filename)
        check(
            f"restoring {filename} from its pristine copy would undo the pack's {key}",
            now != before,
            f"{key}: file says {now!r}, the copy that predates the pack says {before!r}",
        )

    # And the other half of "restoring is a rename": what else would come back with it.
    for filename in ("WillowInput.ini", "WillowGame.ini", "WillowEngine.ini"):
        live = config / filename
        backup = live.with_suffix(live.suffix + gf.ORIGINAL_SUFFIX)
        if not backup.is_file():
            continue
        differing = _keys_that_differ(live, backup)
        strays = differing - PACK_KEYS
        if filename not in writing:
            # The pack writes nothing into this file today, so an identical copy is the honest
            # one and any difference at all is the copy having gone stale against the owner's
            # own later changes. Worth saying, not worth failing over.
            if differing:
                print(f"   ({filename}: the pack writes nothing here now, and its copy has drifted "
                      f"{len(differing)} keys behind the owner's own settings: {sorted(differing)[:4]})")
            continue
        check(
            f"restoring {filename} would change only keys the pack itself wrote",
            not strays,
            f"it would also revert {sorted(strays)}"
            if strays
            else f"{len(differing)} differing keys, all the pack's",
        )
        if filecmp.cmp(live, backup, shallow=False):
            check(
                f"the pristine copy of {filename} is not simply a copy of the edited file",
                False,
                "the two are byte-identical, so the copy was taken after the pack had already "
                "edited this file and restoring it undoes nothing",
            )


def _keys_that_differ(live, backup):
    """
    Which key names hold different values in the two files.

    Values are gathered as a LIST per key, because these files are full of keys that legally
    appear many times in one section - Bindings, +Class, Paths. Keeping one value each made
    every one of those look changed, which is how the first draft of this check reported
    forty differences in WillowEngine.ini when there are three.
    """

    def index(path):
        out: dict = {}
        for section, key, value, _n in sections(path):
            out.setdefault((section, key.lower()), []).append(value)
        return out

    here, there = index(live), index(backup)
    return {key for section, key in set(here) | set(there)
            if here.get((section, key)) != there.get((section, key))}


# --- the log, which is where "already off" either settles or does not ---------------------


def check_the_log():
    if not SDK_LOG.is_file():
        check("there is an sdk log to read configtweaks' own report out of", False, f"{SDK_LOG}")
        return
    lines = [
        line
        for line in SDK_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        if "configtweaks:" in line
    ]
    # The setting names come from the feature's own source, so a fifth setting added later
    # is covered without editing this file. The first-word-after-the-colon idea this replaces
    # was wrong twice over: two of the phrasings start "nothing to change - <name>" and
    # "could not set <name>", so the words counted were "nothing" and "could", and the total
    # landing on four was luck, not coverage.
    feature_src = (
        GAME / "sdk_mods" / "bl2_modern" / "features" / "configtweaks.py"
    ).read_text(encoding="utf-8")
    names = re.findall(r'"(b[A-Z]\w+|PoolSize|PhysXLevel)"', feature_src)
    unspoken = [n for n in dict.fromkeys(names) if not any(n in line for line in lines)]
    check(
        "configtweaks says something about every one of its settings in the log",
        bool(names) and not unspoken,
        f"{len(lines)} configtweaks lines; settings never mentioned: {unspoken or 'none'} "
        f"of {sorted(set(names))}",
    )
    moved = [line.split("configtweaks:")[1].strip() for line in lines if "went from" in line]
    # A change reported on the FIRST launch after a setting is flipped is the feature working.
    # What would be wrong is the same key reported as changing over and over, launch after
    # launch, which is what a capitalisation mismatch used to cause - the pack wrote "false",
    # the game rewrote "False" on exit, and the pack changed it right back next time.
    import collections as _collections

    _keys = _collections.Counter(line.split()[0] for line in moved)
    _repeats = {k: n for k, n in _keys.items() if n > 2}
    check(
        "no setting is being changed back and forth on every launch",
        not _repeats,
        f"{len(moved)} change lines across {len(lines)}; reported more than twice: {_repeats}",
    )


# --- the writer itself, against a throwaway directory -------------------------------------

SAMPLE = (
    "[Engine.PlayerInput]\r\n"
    "bEnableMouseSmoothing=True\r\n"
    "MouseSensitivity=22.000000\r\n"
    "\r\n"
    "[WillowGame.WillowPlayerInput]\r\n"
    "bEnableMouseSmoothing=True\r\n"
    "LastLineHasNoEnding=1"
)


def check_the_writer(gf, sandbox):
    real_config_dir = gf.config_dir
    real_apply = gf.apply_ini_edits
    try:
        gf.config_dir = lambda: sandbox
        target = sandbox / "Fake.ini"
        backup = sandbox / ("Fake.ini" + gf.ORIGINAL_SUFFIX)
        target.write_bytes(SAMPLE.encode("utf-8"))

        changed = gf.edit_ini("Fake.ini", "[Engine.PlayerInput]", {"bEnableMouseSmoothing": "False"})
        written = target.read_bytes()
        check(
            "an edit reports what it moved and moves only the key it was asked for",
            changed == {"bEnableMouseSmoothing": ("True", "False")},
            f"{changed}",
        )
        check(
            "the same key in another section is left alone",
            b"[WillowGame.WillowPlayerInput]\r\nbEnableMouseSmoothing=True" in written,
            f"{written.splitlines()[4:6]}",
        )
        check(
            "the file keeps its CRLF endings and its line count through an edit",
            written.count(b"\r\n") == SAMPLE.encode("utf-8").count(b"\r\n")
            and len(written.splitlines()) == len(SAMPLE.encode("utf-8").splitlines()),
            f"{written.count(b'\r\n')} CRLFs, {len(written.splitlines())} lines",
        )
        check(
            "a last line that had no line ending does not gain one",
            written.endswith(b"LastLineHasNoEnding=1"),
            f"ends {written[-30:]!r}",
        )
        check(
            "a pristine copy of the file appears the first time it is edited",
            backup.is_file() and backup.read_bytes() == SAMPLE.encode("utf-8"),
            f"exists={backup.is_file()}",
        )

        gf.edit_ini("Fake.ini", "[Engine.PlayerInput]", {"bEnableMouseSmoothing": "Maybe"})
        check(
            "a second edit does not overwrite the pristine copy with yesterday's file",
            backup.read_bytes() == SAMPLE.encode("utf-8"),
            f"the copy now says "
            f"{value_in(backup, '[Engine.PlayerInput]', 'bEnableMouseSmoothing')!r}",
        )

        settled = target.read_bytes()
        again = gf.edit_ini("Fake.ini", "[Engine.PlayerInput]", {"bEnableMouseSmoothing": "Maybe"})
        check(
            "writing the value it already holds reports nothing and touches nothing",
            again == {} and target.read_bytes() == settled,
            f"{again}",
        )

        # edit_ini's RETURN is what changed, and all three of these changed nothing - so the
        # return alone can never tell them apart and never could. The third value from
        # apply_ini_edits is what does, and edit_ini turns it into a warning in the log. This
        # asks the layer that actually knows.
        lines = SAMPLE.splitlines(keepends=True)
        _, _, m_correct = gf.apply_ini_edits(
            lines, "[Engine.PlayerInput]", {"bEnableMouseSmoothing": "Maybe"})
        _, _, m_section = gf.apply_ini_edits(
            lines, "[No.Such.Section]", {"bEnableMouseSmoothing": "False"})
        _, _, m_key = gf.apply_ini_edits(
            lines, "[Engine.PlayerInput]", {"bMisspelledKey": "False"})
        check(
            "a key that is not in the file is told apart from a key that was already right",
            m_correct == [] and m_key == ["bMisspelledKey"] and m_section != [] and
            "no such section" in m_section[0],
            f"already-correct={m_correct}, absent key={m_key}, wrong section={m_section}",
        )
        check(
            "and a missing SECTION says so once rather than naming every key in it",
            len(m_section) == 1,
            f"{m_section}",
        )

        # The guard that stands between a bad edit and somebody's settings.
        def _adds_a_line(lines, section, changes):
            # THREE values, not two. apply_ini_edits grew a third - what it could not find - and
            # this stand-in still unpacked two, so it raised a ValueError of its own and the
            # check below reported that instead of testing the guard it exists to test.
            out, moved, missing = real_apply(lines, section, changes)
            return [*out, "SneakedIn=1\r\n"], (moved or {"Sneaked": ("a", "b")}), missing

        gf.apply_ini_edits = _adds_a_line
        before = target.read_bytes()
        blew_up = None
        try:
            gf.edit_ini("Fake.ini", "[Engine.PlayerInput]", {"bEnableMouseSmoothing": "False"})
        except Exception as ex:  # noqa: BLE001
            blew_up = ex
        check(
            "an edit that would change the line count raises and leaves the file alone",
            isinstance(blew_up, RuntimeError) and target.read_bytes() == before,
            f"raised {blew_up!r}",
        )
        gf.apply_ini_edits = real_apply

        # A byte that is not UTF-8, which config files really do collect - a player name, a
        # path with an accent. gamefiles.py:118 reads with errors="replace" and :133 writes
        # the replacement back.
        odd = sandbox / "Odd.ini"
        odd.write_bytes(b"[Engine.PlayerInput]\r\nName=Jos\xe9\r\nbEnableMouseSmoothing=True\r\n")
        gf.edit_ini("Odd.ini", "[Engine.PlayerInput]", {"bEnableMouseSmoothing": "False"})
        after = odd.read_bytes()
        check(
            "editing one key leaves every other byte of the file exactly as it was",
            b"Jos\xe9" in after,
            f"the untouched line came back as {after.splitlines()[1]!r}",
        )
    finally:
        gf.config_dir = real_config_dir
        gf.apply_ini_edits = real_apply


def main():
    gf = load_gamefiles()
    sandbox = pathlib.Path(tempfile.mkdtemp(prefix="bl2-gamefiles-"))
    try:
        check_the_real_config(gf)
        check_texture_buffer(gf)
        check_backups(gf)
        check_the_log()
        check_the_writer(gf, sandbox)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    summary()


if __name__ == "__main__":
    main()
