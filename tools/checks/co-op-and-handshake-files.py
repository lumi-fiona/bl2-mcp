"""
Co-op rules and pause + Version handshake - the claims that live in files on disk.

Run:  python "bl2-mcp/tools/checks/co-op-and-handshake-files.py"

Ordinary Python. No game, no unrealsdk, no harness - it reads WillowGame.ini, the copy the
pack took before it ever touched it, the saved settings, and the feature sources.

One correction to the audit, which the checks below encode rather than repeat: claim 1 says to
assert "any other section's copy of bAdminCanPause is unchanged", on the strength of the sample
in gamefiles.py:139-146 having the key twice. That sample is a synthetic fixture. The real
WillowGame.ini on this machine carries bAdminCanPause exactly once, under [Engine.GameInfo], so
the check that means something is that there is still only one copy - a second one appearing is
what would make the bare-key report at coopfixes.py:39 dangerous.
"""

import importlib.util
import json
import pathlib
import sys

GAME = pathlib.Path(r"Z:\SteamLibrary\steamapps\common\Borderlands 2")
MOD = GAME / "sdk_mods" / "bl2_modern"
SETTINGS = GAME / "sdk_mods" / "settings" / "bl2_modern.json"

ENGINE_GAME_INFO = "[Engine.GameInfo]"
WILLOW_GAME_INFO = "[WillowGame.WillowGameInfo]"
COOP_GAME_INFO = "[WillowGame.WillowCoopGameInfo]"

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


def load_gamefiles():
    """
    gamefiles.py imported straight off disk, without the package around it.

    `import bl2_modern.gamefiles` would drag in mods_base and unrealsdk, neither of which
    exists outside the game. gamefiles.py itself imports nothing but the standard library.
    """
    spec = importlib.util.spec_from_file_location("bl2_gamefiles", MOD / "gamefiles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copies(path, key):
    """Every line in an ini that sets this key, as (line number, section, value)."""
    found = []
    current = None
    for number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1,
    ):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped
        elif "=" in stripped and stripped.partition("=")[0].strip().lower() == key.lower():
            found.append((number, current, stripped.partition("=")[2].strip()))
    return found


def value_in(path, section, key):
    for _number, where, value in copies(path, key):
        if where == section:
            return value
    return None


def saved_option(saved, name):
    """An option's saved value, whether it sits at the top level or inside its group."""
    options = saved.get("options", {})
    if name in options:
        return options[name]
    for group in options.values():
        if isinstance(group, dict) and name in group:
            return group[name]
    return None


def key_of(line):
    stripped = line.strip()
    return stripped.partition("=")[0].strip().lower() if "=" in stripped else stripped


def main():
    gamefiles = load_gamefiles()
    live = gamefiles.config_dir() / "WillowGame.ini"
    original = live.with_suffix(live.suffix + gamefiles.ORIGINAL_SUFFIX)

    check("WillowGame.ini is where the pack looks for it", live.is_file(), str(live))
    check(
        "a copy of WillowGame.ini from before the pack ever touched it is still there",
        original.is_file(),
        str(original),
    )
    if not (live.is_file() and original.is_file()):
        return summary()

    # --- the four levers -------------------------------------------------------------------

    check(
        "bAdminCanPause is true under [Engine.GameInfo]",
        value_in(live, ENGINE_GAME_INFO, "bAdminCanPause") == "true",
        f"reads {value_in(live, ENGINE_GAME_INFO, 'bAdminCanPause')!r}",
    )
    pause_copies = copies(live, "bAdminCanPause")
    check(
        "bAdminCanPause appears in exactly one section, so the bare-key change report cannot "
        "hide a second edit",
        len(pause_copies) == 1 and pause_copies[0][1] == ENGINE_GAME_INFO,
        f"{[(n, s) for n, s, _v in pause_copies]}",
    )
    check(
        "the pack is what flipped it - the pre-pack copy still reads false",
        value_in(original, ENGINE_GAME_INFO, "bAdminCanPause") == "false",
        f"backup reads {value_in(original, ENGINE_GAME_INFO, 'bAdminCanPause')!r}",
    )

    saved = json.loads(SETTINGS.read_text(encoding="utf-8"))
    # Missing from the file means the option's default (both True in coopfixes.py).
    stay_hurt = saved_option(saved, "Bosses stay hurt when you die")
    forget = saved_option(saved, "Enemies forget you while you're down")
    for key, wanted, was in (
        ("bBossesRegenHealthOnReset", "true" if stay_hurt is False else "false", "true"),
        ("bEnemiesForgetDownedPlayers", "false" if forget is False else "true", "false"),
    ):
        check(
            f"{key} is {wanted} under [WillowGame.WillowGameInfo]",
            value_in(live, WILLOW_GAME_INFO, key) == wanted,
            f"reads {value_in(live, WILLOW_GAME_INFO, key)!r}",
        )
        check(
            f"the pack is what changed {key} - the pre-pack copy reads {was}",
            value_in(original, WILLOW_GAME_INFO, key) == was,
            f"backup reads {value_in(original, WILLOW_GAME_INFO, key)!r}",
        )

    check(
        "bEnemiesCannotDoCloseAttacksOnDownedPlayers already shipped true, so the release notes "
        "must not claim that half",
        value_in(live, WILLOW_GAME_INFO, "bEnemiesCannotDoCloseAttacksOnDownedPlayers") == "true"
        and value_in(original, WILLOW_GAME_INFO, "bEnemiesCannotDoCloseAttacksOnDownedPlayers")
        == "true",
        f"live {value_in(live, WILLOW_GAME_INFO, 'bEnemiesCannotDoCloseAttacksOnDownedPlayers')!r}, "
        f"backup "
        f"{value_in(original, WILLOW_GAME_INFO, 'bEnemiesCannotDoCloseAttacksOnDownedPlayers')!r}",
    )

    # [WillowGame.WillowCoopGameInfo] is the class the game actually runs. If it ever carried
    # its own copy of one of these keys, the edit to the parent section would be inert and
    # nothing in the pack would say so.
    overrides = [
        key
        for key in (
            "bResurrectAllPlayersWhenOneDies",
            "bEnemiesForgetDownedPlayers",
            "bBossesRegenHealthOnReset",
            "bAdminCanPause",
        )
        if value_in(live, COOP_GAME_INFO, key) is not None
    ]
    check(
        "the co-op game info section does not override any of the keys the pack sets on its "
        "parent section",
        not overrides,
        f"overridden: {overrides}",
    )

    # --- the option and the file agree ------------------------------------------------------

    option = saved_option(saved, "One death sends both players to New-U")
    check(
        "the saved settings carry the shared-death option at all",
        option is not None,
        f"{SETTINGS} options keys: {sorted(saved.get('options', {}))[:6]}...",
    )
    if option is not None:
        want = "true" if option else "false"
        check(
            "bResurrectAllPlayersWhenOneDies follows the saved option",
            value_in(live, WILLOW_GAME_INFO, "bResurrectAllPlayersWhenOneDies") == want,
            f"option {option!r} wants {want!r}, ini reads "
            f"{value_in(live, WILLOW_GAME_INFO, 'bResurrectAllPlayersWhenOneDies')!r}",
        )
    # Unlike the other three co-op keys, this one is not a fixed value - it follows the option
    # above, so the live file cannot prove what the game shipped. The pre-pack copy can, on its
    # own, regardless of which way the option is currently set.
    check(
        "the pre-pack copy of bResurrectAllPlayersWhenOneDies reads the engine's shipped "
        "default, whatever the option above is set to right now - the backup is a claim about "
        "what the game shipped, not about today's choice",
        value_in(original, WILLOW_GAME_INFO, "bResurrectAllPlayersWhenOneDies") == "false",
        f"backup reads {value_in(original, WILLOW_GAME_INFO, 'bResurrectAllPlayersWhenOneDies')!r}",
    )

    # --- nothing else in the file moved -------------------------------------------------------

    live_lines = live.read_text(encoding="utf-8", errors="replace").splitlines()
    original_lines = original.read_text(encoding="utf-8", errors="replace").splitlines()
    check(
        "the pack's edits did not add or remove a line",
        len(live_lines) == len(original_lines),
        f"{len(original_lines)} lines before, {len(live_lines)} now",
    )
    shared = min(len(live_lines), len(original_lines))
    differ = [i for i in range(shared) if live_lines[i] != original_lines[i]]
    reworded = [i + 1 for i in differ if key_of(live_lines[i]) != key_of(original_lines[i])]
    check(
        "every changed line kept its key and changed only what is after the equals sign",
        not reworded,
        f"lines {reworded}",
    )

    coop_keys = {
        "badmincanpause",
        "bresurrectallplayerswhenonedies",
        "bbossesregenhealthonreset",
        "benemiesforgetdownedplayers",
    }
    changed_keys = {key_of(live_lines[i]) for i in differ}
    # Only bAdminCanPause is always written opposite to what the game ships. The other three
    # follow their options and legitimately equal the pre-pack copy while an option is at vanilla;
    # the backup checks above prove the backup itself is honest regardless.
    must_differ = {"badmincanpause"}
    if option:
        must_differ.add("bresurrectallplayerswhenonedies")
    if stay_hurt is not False:
        must_differ.add("bbossesregenhealthonreset")
    if forget is not False:
        must_differ.add("benemiesforgetdownedplayers")
    check(
        "the co-op keys whose option differs from vanilla differ from the pre-pack copy",
        must_differ <= changed_keys,
        f"missing: {sorted(must_differ - changed_keys)}; changed lines "
        f"{[i + 1 for i in differ]}",
    )
    # blandingshake is configtweaks' "Game feel", not this feature's.
    check(
        "no line outside the co-op keys changed except the one Game feel owns",
        (changed_keys - coop_keys) <= {"blandingshake"},
        f"also changed: {sorted(changed_keys - coop_keys - {'blandingshake'})}",
    )

    # --- what 'every setting already as wanted' can and cannot tell you -----------------------
    #
    # coopfixes.py:55-60 prints that line whenever every edit_ini call came back empty. These
    # two checks ask whether an empty result can be told apart from a satisfied one. It cannot,
    # so both are expected to fail - that IS claim 10, demonstrated rather than asserted.

    sample = [
        "[Engine.GameInfo]\r\n",
        "bAdminCanPause=true\r\n",
        "[WillowGame.WillowGameInfo]\r\n",
        "bBossesRegenHealthOnReset=false\r\n",
    ]
    _, satisfied, satisfied_missing = gamefiles.apply_ini_edits(
        sample, WILLOW_GAME_INFO, {"bBossesRegenHealthOnReset": "false"},
    )
    _, mistyped, mistyped_missing = gamefiles.apply_ini_edits(
        sample, "[WillowGame.WillowGameinfo]", {"bBossesRegenHealthOnReset": "true"},
    )
    _, renamed, renamed_missing = gamefiles.apply_ini_edits(
        sample, WILLOW_GAME_INFO, {"bBossesRegenHealthOnResetV2": "true"},
    )
    # apply_ini_edits gained a third return value on 2026-08-20 naming what it could not find,
    # precisely so these three cases stop looking identical. Compare the whole answer.
    check(
        "a mistyped section constant reports something different from a setting already as wanted",
        (satisfied, satisfied_missing) != (mistyped, mistyped_missing),
        f"already-correct came back {satisfied!r} {satisfied_missing!r}, "
        f"mistyped came back {mistyped!r} {mistyped_missing!r}",
    )
    check(
        "a key the game has renamed or dropped reports something different from a setting "
        "already as wanted",
        (satisfied, satisfied_missing) != (renamed, renamed_missing),
        f"already-correct came back {satisfied!r} {satisfied_missing!r}, "
        f"renamed key came back {renamed!r} {renamed_missing!r}",
    )

    # --- the handshake's own files -------------------------------------------------------------

    handshake_source = (MOD / "features" / "handshake.py").read_text(encoding="utf-8")
    check(
        "a mismatch reaches the player's screen, not only the log",
        "show_hud_message" in handshake_source,
        "handshake.py's only sink is logging.error at :47, while ui_utils.show_hud_message is "
        "already imported and used seven times in features/grinder.py - so 'Warns when two "
        "players are not running the identical pack' is not true of the running program",
    )

    shipped = sorted(p.name for p in (MOD / "data").glob("*.txt"))
    hashed = [name for name in shipped if f'"{name}"' in handshake_source]
    patch_files = sorted({
        name
        for name in shipped
        if any(
            f'patch_file="{name}"' in source.read_text(encoding="utf-8")
            for source in (MOD / "features").glob("*.py")
        )
        or name == "patch.txt"
    })
    check(
        "every patch file the features ship is named in the fingerprint",
        set(patch_files) <= set(hashed),
        f"features ship {patch_files}, handshake.py names {hashed}; data/ holds {shipped}",
    )

    return summary()


if __name__ == "__main__":
    good, total = main()
    sys.exit(0 if good == total else 1)
