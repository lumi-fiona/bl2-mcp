# Sanity Saver, the claim that needs time to pass - AUDIT-RAW/sanity-saver.md claim 9
# ("with it on, an item whose parts the game does not recognise survives a save")
#
# This file is run TWICE. The first run photographs the sidecars and the backpack, the second
# compares them. It never saves the game itself - a check that overwrites a real save to prove
# saving works is a worse trade than asking the operator to press the button.
#
# Sequence, with a character already loaded and standing somewhere safe:
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   2. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/save-backup-and-sanity-needs-travel.py
#        -> prints "PHASE 1" and what it photographed
#   3. In the game, make the game save: fast travel to another station, or walk through a level
#      transition, or quit to the main menu and load the character back. Do NOT sell, drop,
#      grind or equip anything in between - an item you got rid of on purpose leaves its sidecar
#      entry behind and reads here as a loss.
#   4. Wait until the map has finished loading and you can move. sleep 20 is plenty.
#   5. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/save-backup-and-sanity-needs-travel.py
#        -> prints "PHASE 2" and the checks
#
# What is still NOT proven by this: that the parts come back after the game is closed and
# reopened. That needs a relaunch and a character load through game_load_character, and the
# comparison to make afterwards is the id -> name list phase 1 prints.

reset()

import gzip
import json
import sys
from pathlib import Path


def sidecar_dir():
    module = next(
        (m for k, m in list(sys.modules.items()) if k.endswith("SanitySaver.save_manager")),
        None,
    )
    if module is not None:
        return Path(module._SAVES_DIR)
    return Path(r"Z:/SteamLibrary/steamapps/common/Borderlands 2/sdk_mods/SanitySaver/Saves")


def save_dir():
    from bl2_modern.gamefiles import savedata_dir

    root = savedata_dir()
    accounts = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    return accounts[0] if len(accounts) == 1 else None


def read_sidecars():
    out = {}
    for path in sorted(sidecar_dir().glob("*.json.gz")):
        try:
            items = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8")).get("items", {})
        except Exception as ex:  # noqa: BLE001
            items = {"unreadable": repr(ex)}
        stat = path.stat()
        out[path.name] = {
            "mtime": stat.st_mtime_ns,
            "size": stat.st_size,
            "ids": frozenset(str(k) for k in items),
        }
    return out


def read_saves():
    account = save_dir()
    if account is None:
        return {}
    return {p.name: p.stat().st_mtime_ns for p in sorted(account.glob("Save*.sav"))}


def carried():
    out = {}
    for item in backpack() + equipped():
        try:
            out[str(int(item.DefinitionData.UniqueId))] = str(item.GetShortHumanReadableName())
        except Exception:  # noqa: BLE001, PERF203 - a stub item is not worth aborting for
            continue
    return out


snapshot = globals().get("_SANITY_SIDECAR_SNAPSHOT")

if snapshot is None:
    _SANITY_SIDECAR_SNAPSHOT = {
        "sidecars": read_sidecars(),
        "saves": read_saves(),
        "carried": carried(),
        "where": where(),
    }
    photo = _SANITY_SIDECAR_SNAPSHOT
    print("PHASE 1 - photographed, now make the game save (see the top of this file)")
    print(f"   map:      {photo['where']}")
    print(f"   saves:    {sorted(photo['saves'])}")
    print(f"   carrying: {len(photo['carried'])} items")
    for name, data in photo["sidecars"].items():
        print(f"   sidecar {name}: {len(data['ids'])} items, {data['size']} bytes")
    protected = {i: n for i, n in photo["carried"].items()
                 if any(i in d["ids"] for d in photo["sidecars"].values())}
    print(f"   of what is carried, Sanity Saver is holding parts for {len(protected)}:")
    for uid, name in list(protected.items())[:20]:
        print(f"      {uid}  {name}")
    check(
        "there is something to watch: a sidecar with items in it",
        any(data["ids"] for data in photo["sidecars"].values()),
        f"{len(photo['sidecars'])} sidecars on disk",
    )
    check(
        "the backpack can be read, so the second run has something to compare",
        len(photo["carried"]) > 0,
        f"{len(photo['carried'])} items carried",
    )
else:
    print("PHASE 2 - comparing against the photograph")
    now_sidecars = read_sidecars()
    now_saves = read_saves()
    now_carried = carried()

    moved = [
        name for name, mtime in now_saves.items() if snapshot["saves"].get(name) != mtime
    ]
    check(
        "the game wrote a save between the two runs",
        bool(moved),
        f"saves rewritten: {moved} - if this is empty the game never saved and nothing below "
        "means anything yet",
    )

    written = [
        name
        for name, data in now_sidecars.items()
        if snapshot["sidecars"].get(name, {}).get("mtime") != data["mtime"]
    ]
    check(
        "Sanity Saver wrote its item parts out when the game saved",
        bool(written),
        f"sidecars rewritten: {written}. Nothing rewritten while a save was written means the "
        "mod is registered but not running - which is what 'already on' hides",
    )

    lost = {}
    for name, before in snapshot["sidecars"].items():
        after = now_sidecars.get(name)
        gone = before["ids"] - (after["ids"] if after else frozenset())
        if gone:
            lost[name] = sorted(gone)[:10]
    check(
        "no item Sanity Saver was already protecting dropped out of its sidecar",
        not lost,
        f"ids no longer in their sidecar: {lost}",
    )

    was_protected = {
        uid: name
        for uid, name in snapshot["carried"].items()
        if any(uid in data["ids"] for data in snapshot["sidecars"].values())
    }
    vanished = {uid: name for uid, name in was_protected.items() if uid not in now_carried}
    check(
        "every item whose parts Sanity Saver was holding is still being carried",
        not vanished,
        f"{len(was_protected)} items were protected, {len(vanished)} are gone: "
        f"{list(vanished.values())[:10]}",
    )

    _SANITY_SIDECAR_SNAPSHOT = None
    print("photograph cleared - the next run starts a new phase 1")

summary()
