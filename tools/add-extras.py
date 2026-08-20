"""
Splice one more downloaded text mod into data/extras.txt, without rebuilding the rest.

    python bl2-mcp/tools/add-extras.py "<source.blcm>" "<section name>" "<what it does>"

build_extras.py rebuilds the whole file from a folder of downloaded sources, which is the right
tool when every source is on disk. The four sections shipped before 2026-08-20 were built from
files that were downloaded once and not kept, so a rebuild today would silently drop them - the
script prints MISSING and carries on. This adds one section instead, leaving everything already
in the file exactly as it is, and verifies the whole file still reads back through the pack's own
parser afterwards.

Both halves of the same rule as build_extras: commands a source ships switched OFF are dropped,
and a command tied to one map is carried through as a hotfix naming that map, because the pack
holds those back and fires them when that map loads.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent.parent / "sdk_mods" / "bl2_modern"
sys.path.insert(0, str(PACK))

from patchfile import commands_from, sections_in  # noqa: E402

TARGET = PACK / "data" / "extras.txt"
CLOSE = "\t\t</category>\n\t</body>\n"


def add(source: Path, section: str, what: str) -> None:
    text = TARGET.read_text(encoding="utf-8")
    if f'<category name="{html.escape(section)}">' in text:
        print(f"{section!r} is already in {TARGET.name} - nothing to do")
        return
    if CLOSE not in text:
        msg = f"{TARGET} does not end the way this script expects; not touching it"
        raise SystemExit(msg)

    before = commands_from(text)
    commands, hotfixes, ignored = commands_from(
        source.read_text(encoding="utf-8", errors="replace"),
    )
    if not commands and not hotfixes:
        msg = f"{source.name} parsed to nothing ({ignored} lines ignored); refusing to add it"
        raise SystemExit(msg)

    block = [f'\t\t\t<category name="{html.escape(section)}">\n']
    block.append(f"\t\t\t\t<comment># {html.escape(what)}</comment>\n")
    block.append(f"\t\t\t\t<comment># Built from {html.escape(source.name)}</comment>\n")
    for command in commands:
        block.append(f'\t\t\t\t<code profiles="default">{html.escape(command)}</code>\n')
    for level, command in hotfixes:
        block.append(
            f'\t\t\t\t<hotfix name="{html.escape(section)}" level="{html.escape(level)}">\n',
        )
        block.append(f'\t\t\t\t\t<code profiles="default">{html.escape(command)}</code>\n')
        block.append("\t\t\t\t</hotfix>\n")
    block.append("\t\t\t</category>\n")

    TARGET.write_text(text.replace(CLOSE, "".join(block) + CLOSE, 1), encoding="utf-8")

    # Read the whole thing back with the parser the game will use. Anything lost or gained
    # anywhere else in the file is a bug in this script and better found here than in a save.
    after_text = TARGET.read_text(encoding="utf-8")
    after = commands_from(after_text)
    found = sections_in(after_text)
    grew_plain = len(after[0]) - len(before[0])
    grew_hotfix = len(after[1]) - len(before[1])
    assert grew_plain == len(commands), f"plain commands moved by {grew_plain}, added {len(commands)}"
    assert grew_hotfix == len(hotfixes), f"map commands moved by {grew_hotfix}, added {len(hotfixes)}"
    assert found.get(section, 0) == len(commands) + len(hotfixes), (
        f"{section}: wrote {len(commands) + len(hotfixes)}, read back {found.get(section, 0)}"
    )
    print(
        f"added {section!r}: {len(commands)} commands and {len(hotfixes)} map-gated ones, "
        f"{ignored} lines ignored. The file now holds {len(found)} sections and "
        f"{len(after[0]) + len(after[1])} commands.",
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    add(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
