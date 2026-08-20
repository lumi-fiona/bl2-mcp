"""
Turn a night's log into a page about last night.

    python bl2-mcp/tools/night-log.py                 # the most recent night
    python bl2-mcp/tools/night-log.py --all           # every night on disk
    python bl2-mcp/tools/night-log.py <file.jsonl>    # one particular file
    python bl2-mcp/tools/night-log.py --out page.md   # write it somewhere instead of printing

Plain python. It never touches the game, never launches it, and only reads.

The log is written by sdk_mods/bl2_modern/features/nightlog.py, one JSON object per line. Every
field this reads is optional: a line missing something is written around rather than skipped, and
a line that will not parse at all is counted and mentioned at the bottom, because a silently
dropped line is how a night ends up looking quieter than it was.

Map names are the game's own internal ones - "SouthpawFactory_P". Turning that into "Southpaw
Factory" is a guess made here rather than in the mod, so a wrong guess costs a rewrite of this
file and not a game restart. The real name is always kept alongside it.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent.parent
NIGHTS = GAME / "sdk_mods" / "bl2_modern" / "data" / "nights"

# Places whose split-the-camel-case version reads wrong. Only the ones actually seen go in here -
# an invented list of ninety map names would be ninety more things to be wrong about.
KNOWN = {
    "sanctuary_p": "Sanctuary",
    "southpawfactory_p": "The Southpaw Steam & Power Plant",
    "grass_p": "The Highlands",
    "icecanyon_p": "Three Horns Valley",
    "frost_p": "Three Horns Divide",
    "fyrestone_p": "Arid Nexus",
    "loader": "the main menu",
}


def pretty_place(raw):
    """A readable name for a map. A guess, always shown next to the real one."""
    if not raw:
        return "somewhere"
    key = str(raw).lower()
    if key in KNOWN:
        return KNOWN[key]
    name = re.sub(r"_p$", "", str(raw), flags=re.IGNORECASE)
    name = name.replace("_", " ")
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return name.strip() or str(raw)


def clock(stamp):
    try:
        return datetime.fromtimestamp(float(stamp)).strftime("%H:%M")
    except Exception:
        return "??:??"


def read(path):
    """Every event in a file, plus how many lines would not parse."""
    events, broken = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            broken += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            broken += 1
    return events, broken


def spell_seconds(total):
    total = int(total)
    if total < 60:
        return f"{total} seconds"
    if total < 3600:
        return f"{total // 60} minutes"
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes:02d}m" if minutes else f"{hours} hours"


def page(events, broken, name):
    """The whole write-up for one night."""
    out = []
    firsts = [e.get("at") for e in events if isinstance(e.get("at"), (int, float))]
    began, ended = (min(firsts), max(firsts)) if firsts else (0, 0)

    when = datetime.fromtimestamp(began).strftime("%A %d %B, from %H:%M") if began else name
    out.append(f"# {when}")
    out.append("")
    if began and ended > began:
        out.append(f"You played for {spell_seconds(ended - began)}.")
        out.append("")

    header = next((e for e in events if e.get("kind") == "night began"), None)
    if header and not header.get("on_the_host", True):
        out.append(f"> {header.get('note', '')}")
        out.append("")

    kills = [e for e in events if e.get("kind") == "killed"]
    pickups = [e for e in events if e.get("kind") == "picked up"]
    downs = [e for e in events if e.get("kind") == "went down"]
    drops = [e for e in events if e.get("kind") == "dropped"]

    # --- the shape of the night, one paragraph -------------------------------------------
    who_killed = Counter(e.get("by", "someone") for e in kills)
    line = f"{len(kills)} things died"
    if len(who_killed) > 1:
        line += " (" + ", ".join(f"{n} to {w}" for w, n in who_killed.most_common()) + ")"
    line += f", {len(drops)} of them left something behind"
    line += f", and {len(pickups)} things were picked up."
    if downs:
        who_down = Counter(e.get("who", "someone") for e in downs)
        line += " " + ", ".join(f"{w} went down {n} times" for w, n in who_down.most_common()) + "."
    else:
        line += " Nobody went down."
    out.append(line)
    out.append("")

    # --- where you went, in order ---------------------------------------------------------
    out.append("## Where you went")
    out.append("")
    visits = [e for e in events if e.get("kind") == "arrived"]
    if not visits:
        out.append("The log never saw the map change, so this was all one place.")
    for visit in visits:
        raw = visit.get("where", "")
        out.append(f"- **{clock(visit.get('at'))}** {pretty_place(raw)}  `{raw}`")
    out.append("")

    # --- what died, by area ---------------------------------------------------------------
    out.append("## What died")
    out.append("")
    by_place = {}
    for kill in kills:
        by_place.setdefault(kill.get("where", ""), []).append(kill)
    if not by_place:
        out.append(
            "Nothing. If you were the guest in somebody else's game that is expected - enemies "
            "die on the host's machine and their log has them.",
        )
    for place, here in sorted(by_place.items(), key=lambda pair: -len(pair[1])):
        timed = [k["took_seconds"] for k in here if isinstance(k.get("took_seconds"), (int, float))]
        middle = sorted(timed)[len(timed) // 2] if timed else None
        out.append(f"### {pretty_place(place)}  `{place}`")
        out.append("")
        out.append(
            f"{len(here)} killed"
            + (f", typically {middle:.1f} seconds each" if middle else "")
            + ".",
        )
        out.append("")
        counted = Counter(k.get("what", "something") for k in here)
        for what, count in counted.most_common(12):
            slowest = max(
                (k.get("took_seconds") or 0 for k in here if k.get("what") == what),
                default=0,
            )
            out.append(
                f"- {what} x{count}" + (f" (worst took {slowest:.1f}s)" if slowest else ""),
            )
        if len(counted) > 12:
            out.append(f"- and {len(counted) - 12} other sorts")
        out.append("")

    # --- the loot ---------------------------------------------------------------------------
    out.append("## What you came away with")
    out.append("")
    if not pickups:
        out.append(
            "Nothing was recorded. Either nothing was picked up, or the pickup hook the mod "
            "guesses at is the wrong one - nightlog.py says which spellings it tried.",
        )
    gear = [p for p in pickups if p.get("sort") != "WillowUsableItem"]
    for who, taken in sorted(
        _group(gear, "by").items(),
        key=lambda pair: -len(pair[1]),
    ):
        out.append(f"### {who}")
        out.append("")
        for pickup in taken:
            rarity = pickup.get("rarity")
            stars = f" ({'rarity ' + str(rarity)})" if rarity else ""
            out.append(
                f"- **{clock(pickup.get('at'))}** {pickup.get('what', 'something')}{stars} "
                f"in {pretty_place(pickup.get('where'))}",
            )
        out.append("")

    # --- the bad moments ----------------------------------------------------------------------
    if downs:
        out.append("## When it went wrong")
        out.append("")
        for down in downs:
            out.append(
                f"- **{clock(down.get('at'))}** {down.get('who', 'someone')} went down in "
                f"{pretty_place(down.get('where'))}",
            )
        out.append("")

    if broken:
        out.append(
            f"*{broken} lines of the log could not be read and are not counted above.*",
        )
        out.append("")
    out.append(f"*From {name}, {len(events)} events.*")
    return "\n".join(out)


def _group(events, key):
    grouped = {}
    for event in events:
        grouped.setdefault(str(event.get(key, "someone")), []).append(event)
    return grouped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="a night's .jsonl file; the newest if left out")
    parser.add_argument("--all", action="store_true", help="every night on disk, newest first")
    parser.add_argument("--out", help="write to this file instead of printing")
    parser.add_argument("--folder", default=str(NIGHTS), help="where the logs live")
    args = parser.parse_args()

    folder = Path(args.folder)
    if args.file:
        chosen = [Path(args.file)]
    else:
        found = sorted(folder.glob("night-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            print(f"No logs in {folder}. Play a bit with the night's log switched on.")
            return 1
        chosen = found if args.all else found[:1]

    pages = []
    for path in chosen:
        if not path.is_file():
            print(f"No such file: {path}")
            return 1
        events, broken = read(path)
        pages.append(page(events, broken, path.name))

    text = "\n\n---\n\n".join(pages)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}, {len(text)} characters from {len(chosen)} files.")
    else:
        print(text)
    return 0


def demo():
    """
    The one check this file leaves behind. Fails if the write-up stops handling a real log.

    Deliberately includes the three shapes that actually break readers: a line that is not JSON,
    an event missing the fields the reader wants, and a night with nothing in it at all.
    """
    events = [
        {"at": 1700000000, "kind": "night began", "where": "Grass_P", "on_the_host": True},
        {"at": 1700000001, "kind": "arrived", "where": "Grass_P", "left": None},
        {"at": 1700000005, "kind": "killed", "where": "Grass_P", "what": "Skag", "by": "Lumi",
         "took_seconds": 3.5, "experience": 120},
        {"at": 1700000006, "kind": "killed", "where": "Grass_P"},  # every field missing
        {"at": 1700000009, "kind": "dropped", "where": "Grass_P", "what": "Skag"},
        {"at": 1700000010, "kind": "picked up", "where": "Grass_P", "what": "Hornet",
         "by": "Lumi", "sort": "WillowWeapon", "rarity": 3},
        {"at": 1700003600, "kind": "went down", "where": "Grass_P", "who": "Lumi"},
    ]
    text = page(events, 1, "night-test.jsonl")
    assert "Skag" in text, text
    assert "Hornet" in text, text
    assert "Lumi went down 1 times" in text, text
    assert "1 lines of the log could not be read" in text, text
    assert "The Highlands" in text, text
    assert "1 hours" in text or "60 minutes" in text, text

    empty = page([], 0, "night-empty.jsonl")
    assert "0 events" in empty, empty
    assert "Nothing." in empty, empty

    # A guest's log: the reader must say why it is empty rather than looking broken.
    guest = page(
        [{"at": 1700000000, "kind": "night began", "on_the_host": False, "note": "joined"}],
        0,
        "night-guest.jsonl",
    )
    assert "joined" in guest, guest
    print("night-log demo: all checks passed")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        sys.exit(main())
