"""
Rebuild the ".original" copies of the game's ini files so they are honest again.

    python bl2-mcp/tools/rebuild-pristine-inis.py [--write]

WHAT WENT WRONG. gamefiles.edit_ini keeps a copy of each ini beside it, named `<file>.original`,
taken once and never again, so that a mistake can be undone without a reinstall. The copy is
taken just before the first write - which is the right moment, except that the pack had already
been editing these files for a while by the time that mechanism was added. So the copies were
taken from files the pack had already changed, and restoring one would put the pack's own edits
straight back. Measured 2026-08-20: WillowInput.ini and its .original are byte-identical, and so
were the four co-op keys (bAdminCanPause, bBossesRegenHealthOnReset, bEnemiesForgetDownedPlayers,
bResurrectAllPlayersWhenOneDies) in WillowGame.ini and its .original - coopfixes.py had been
writing all four since before this script existed.

A file that claims to predate the pack and does not is worse than no file at all, because
somebody reaching for it in a panic would believe they had undone something.

WHAT THIS DOES. The pack writes six keys across these two files. What the game ships for each
one is read out of the game's own shipped config, not remembered:

    WillowInput.ini
        bEnableMouseSmoothing            true    Engine/Config/BaseInput.ini:8
    WillowGame.ini
        bLandingShake                    true    WillowGame/Config/DefaultGame.ini:115
        bAdminCanPause                   false   Engine/Config/BaseGame.ini:5
        bResurrectAllPlayersWhenOneDies  false   WillowGame/Config/DefaultGame.ini:78
        bBossesRegenHealthOnReset        true    WillowGame/Config/DefaultGame.ini:79
        bEnemiesForgetDownedPlayers      false   WillowGame/Config/DefaultGame.ini:80

So an honest copy is the file as it stands now with those put back. Every other byte in there is
the owner's own setting and the pack never touched it, which is why this rebuilds from the live
file rather than from the shipped defaults - copying the shipped file over would throw away a
resolution, a keybind and a difficulty setting to undo six booleans.

WillowGame.ini carries five of the six keys, in three different sections, so the live file is
read once per FILE and every one of that file's keys is put back into the same in-memory copy
before anything is written. Writing after each key - starting from a freshly re-read live file
every time, the way this script used to - would make each write erase the one before it and
leave only the last key in the list actually reverted.

Prints what it would do and changes nothing unless given --write.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent.parent
CONFIG = Path.home() / "Documents" / "My Games" / "Borderlands 2" / "WillowGame" / "Config"
SUFFIX = ".bl2_modern_original"  # matches gamefiles.ORIGINAL_SUFFIX

# (file, section, key, what the game ships, where that was read from)
PACK_WRITES = [
    (
        "WillowInput.ini",
        "[Engine.PlayerInput]",
        "bEnableMouseSmoothing",
        "True",
        "Engine/Config/BaseInput.ini:8",
    ),
    (
        "WillowGame.ini",
        "[WillowGame.WillowPlayerController]",
        "bLandingShake",
        "True",
        "WillowGame/Config/DefaultGame.ini:115",
    ),
    # The four co-op keys coopfixes.py writes. Case matches the shipped ini files themselves
    # (lower-case), not the "True" above - both the source files and co-op-and-handshake-files.py
    # compare these four case-sensitively, so an inherited "True" would silently fail that check.
    (
        "WillowGame.ini",
        "[Engine.GameInfo]",
        "bAdminCanPause",
        "false",
        "Engine/Config/BaseGame.ini:5",
    ),
    (
        "WillowGame.ini",
        "[WillowGame.WillowGameInfo]",
        "bResurrectAllPlayersWhenOneDies",
        "false",
        "WillowGame/Config/DefaultGame.ini:78",
    ),
    (
        "WillowGame.ini",
        "[WillowGame.WillowGameInfo]",
        "bBossesRegenHealthOnReset",
        "true",
        "WillowGame/Config/DefaultGame.ini:79",
    ),
    (
        "WillowGame.ini",
        "[WillowGame.WillowGameInfo]",
        "bEnemiesForgetDownedPlayers",
        "false",
        "WillowGame/Config/DefaultGame.ini:80",
    ),
]

_SECTION = re.compile(r"^\s*\[[^\]]+\]")


def put_back(lines: list[str], section: str, key: str, value: str) -> tuple[list[str], bool]:
    """One key, in one section, back to the value the game ships. Line count never changes."""
    out = list(lines)
    current = None
    for i, line in enumerate(out):
        if _SECTION.match(line):
            current = line.strip()
            continue
        if current != section:
            continue
        match = re.match(r"^(\s*)(" + re.escape(key) + r")(\s*=\s*)(.*?)(\r?\n?)$", line, re.I)
        if match is None:
            continue
        indent, name, equals, old, ending = match.groups()
        if old.strip().lower() == value.lower():
            return out, False
        out[i] = f"{indent}{name}{equals}{value}{ending}"
        return out, True
    return out, False


def main(write: bool) -> None:
    # Grouped by file: WillowGame.ini carries five of the six keys, and each must be put back
    # into the SAME rebuilt copy. Looping per-key and re-reading the live file every time (as
    # this used to) would make each file's last write win and silently discard the rest.
    by_file: dict[str, list[tuple[str, str, str, str]]] = {}
    for filename, section, key, shipped, source in PACK_WRITES:
        by_file.setdefault(filename, []).append((section, key, shipped, source))

    for filename, writes in by_file.items():
        path = CONFIG / filename
        copy = path.with_suffix(path.suffix + SUFFIX)
        if not path.is_file():
            print(f"{filename}: not on this machine, skipping")
            continue

        # latin-1 for the same reason gamefiles.py uses it: these files hold a player name, and
        # a byte that is not valid UTF-8 must survive being read and written.
        lines = path.read_text(encoding="latin-1").splitlines(keepends=True)
        was = "identical to the live file" if copy.is_file() and copy.read_bytes() == path.read_bytes() else (
            "already differs from the live file" if copy.is_file() else "absent"
        )

        rebuilt = lines
        for section, key, shipped, source in writes:
            rebuilt, moved = put_back(rebuilt, section, key, shipped)
            print(f"{filename}: copy was {was}; {key} -> {shipped} ({'changed' if moved else 'already right'})")
            print(f"    the shipped value came from {source}")

        if not write:
            continue

        if copy.is_file():
            shutil.copy2(copy, copy.with_suffix(copy.suffix + ".superseded"))
        copy.write_text("".join(rebuilt), encoding="latin-1")
        print(f"    wrote {copy.name} ({len(rebuilt)} lines, the live file has {len(lines)})")
        assert len(rebuilt) == len(lines), "a rebuilt copy must have the same number of lines"


if __name__ == "__main__":
    main("--write" in sys.argv)
