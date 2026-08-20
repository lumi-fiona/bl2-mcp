# Display + ultra-wide - the claims that can be settled from files on disk.
# Run: python "bl2-mcp/tools/checks/display-and-ultrawide-files.py"
#
# Ordinary Python. No game, no harness, no unrealsdk - it reads three files:
#
#   sdk_mods/bl2_modern/features/display.py     which slider writes which property
#   sdk_mods/bl2_modern/features/ultrawide.py   how many menus its docstring claims to fix
#   WillowGame/Localization/INT/WillowMenu.int  what the GAME calls those same properties
#
# The last one is the point. The audit suspects "HUD size" is wired to the wrong properties,
# and the game ships the answer in its own menu text.

import ast
import re
from pathlib import Path

GAME = Path(__file__).resolve().parents[3]
DISPLAY = GAME / "sdk_mods" / "bl2_modern" / "features" / "display.py"
ULTRAWIDE = GAME / "sdk_mods" / "bl2_modern" / "features" / "ultrawide.py"
MENU_TEXT = GAME / "WillowGame" / "Localization" / "INT" / "WillowMenu.int"
ULTRAWIDE_DOC = GAME / "BL2-ULTRAWIDE.md"

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


def read_text(path):
    """
    The .int files are UTF-16 with a BOM; the .py and .md files are UTF-8.

    The BOM is checked rather than guessed at: decoding a UTF-8 file as UTF-16 usually
    succeeds and returns mojibake, which then quietly matches no regex at all.
    """
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16").replace("\r", "")
    return raw.decode("utf-8", "replace").replace("\r", "")


def sliders(tree):
    """{variable name: (label, value, min, max)} for every module-level SliderOption."""
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        called = node.value.func
        if getattr(called, "id", getattr(called, "attr", None)) != "SliderOption":
            continue
        args = [a.value if isinstance(a, ast.Constant) else None for a in node.value.args]
        out[node.targets[0].id] = tuple(args[:4])
    return out


def written_properties(tree):
    """{variable name: {property names it is written to}} from _apply_to's mapping."""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
            continue
        name, option = node.elts
        if isinstance(name, ast.Constant) and isinstance(name.value, str) and isinstance(option, ast.Name):
            out.setdefault(option.id, set()).add(name.value)
    return out


def menu_labels(text):
    """{property: (the game's label, the game's description)} out of WillowMenu.int."""
    out = {}
    for prop in ("HUDScaleX", "HUDScaleY", "HUDScaleE"):
        label = re.search(rf'^{prop}="(.*)"$', text, re.M)
        desc = re.search(rf"^{prop}Desc=(.*)$", text, re.M)
        out[prop] = (
            label.group(1) if label else None,
            desc.group(1).strip() if desc else None,
        )
    return out


def main():
    display_src = read_text(DISPLAY)
    display_tree = ast.parse(display_src)
    slider = sliders(display_tree)
    writes = written_properties(display_tree)
    by_label = {
        spec[0]: writes.get(var, set())
        for var, spec in slider.items()
    }
    labels = menu_labels(read_text(MENU_TEXT))

    check(
        "the game's own menu text calls HUDScaleE the size of all HUD elements",
        labels["HUDScaleE"][1] is not None
        and "size of all HUD elements" in labels["HUDScaleE"][1],
        f"WillowMenu.int says {labels['HUDScaleE'][0]!r}: {labels['HUDScaleE'][1]!r}",
    )
    check(
        "the game's own menu text calls HUDScaleX and HUDScaleY bounds, not size",
        all(
            labels[p][0] is not None and "BOUNDS" in labels[p][0].upper()
            for p in ("HUDScaleX", "HUDScaleY")
        ),
        f"WillowMenu.int says {labels['HUDScaleX'][0]!r} / {labels['HUDScaleY'][0]!r}: "
        f"{labels['HUDScaleX'][1]!r}",
    )

    check(
        "the slider called 'HUD size' writes the property the game calls the size of all "
        "HUD elements",
        "HUDScaleE" in by_label.get("HUD size", set()),
        f"'HUD size' writes {sorted(by_label.get('HUD size', set()))}, which the game calls "
        f"{labels['HUDScaleX'][0]!r} / {labels['HUDScaleY'][0]!r} - raising it spreads the HUD "
        f"toward the screen edges instead of enlarging it",
    )
    # There is no slider called "HUD text size" any more - it was renamed to "How far the HUD
    # sits from the screen edges" on 2026-08-19, once the game's own menu text showed it was
    # never a text lever at all. A check that still hunts for that exact old name silently
    # passes vacuously (by_label.get returns an empty set, any() over nothing is False - which
    # used to print as a FAIL forever, not a PASS). So this looks for the LIE itself, under any
    # label, rather than one label string that is already gone: no slider name may claim "text"
    # unless the property it writes is one the game itself describes as text, and the slider
    # that writes the position-only properties (HUDScaleX/Y) may not claim "size" either - that
    # was the other half of the same swap.
    check(
        "no slider claims to move text specifically - none of these three properties are "
        "text-only, and 'HUD text size' was that exact claim until it was renamed away",
        not any("text" in label.lower() for label in by_label),
        f"current slider labels: {sorted(by_label)}",
    )
    bounds_writers = [
        label for label, props in by_label.items() if props & {"HUDScaleX", "HUDScaleY"}
    ]
    check(
        "the slider that writes the position-only bounds properties doesn't claim to change size",
        bool(bounds_writers) and all("size" not in label.lower() for label in bounds_writers),
        f"{bounds_writers} writes HUDScaleX/HUDScaleY, which the game calls "
        f"{labels['HUDScaleX'][0]!r} / {labels['HUDScaleY'][0]!r} - a position, not a size",
    )

    def module_const(tree, name):
        """A module-level `NAME = <number>` constant, or None if there is no such line."""
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name
                and isinstance(node.value, ast.Constant)
            ):
                return node.value.value
        return None

    # Compared against NARROWEST, not the SliderOption's own min. The slider's min is 0, and 0
    # is a sentinel meaning "leave the game's own setting alone" - it was never a real floor, so
    # a docstring claiming the range starts at 0 would be describing the sentinel, not the
    # narrowest field of view the slider actually lets you dial in.
    narrowest = module_const(display_tree, "NARROWEST")
    advertised = re.search(r"this offers (\d+) to (\d+)", display_src)
    fov = slider.get("fov")
    check(
        "the field of view range the module docstring advertises is the one the slider offers",
        advertised is not None
        and fov is not None
        and narrowest is not None
        and (float(advertised.group(1)), float(advertised.group(2)))
        == (float(narrowest), float(fov[3])),
        f"docstring says {advertised.groups() if advertised else None}, "
        f"NARROWEST is {narrowest}, SliderOption max is {fov[3] if fov else None}",
    )

    ultrawide_src = read_text(ULTRAWIDE)
    doc = read_text(ULTRAWIDE_DOC)
    measured = re.findall(r"^\|\s*`(UI_[\w.]+)`", doc, re.M)
    said = re.search(r"(\w+)\s+of\s+them\s+are\s+set\s+to\s+the\s+scale\s+mode\s+SM_NoBorder",
                     ultrawide_src)
    words = {"Five": 5, "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9}
    check(
        "the number of SM_NoBorder menus the docstring names is the number the pack measured",
        said is not None and words.get(said.group(1).capitalize()) == len(measured),
        f"ultrawide.py says {said.group(1) if said else None}; BL2-ULTRAWIDE.md's table lists "
        f"{len(measured)} definitions at SM_NoBorder ({measured}) - the scope is on that list "
        f"because it is SM_NoBorder too, it is only excluded from the fix",
    )

    return summary()


if __name__ == "__main__":
    good, total = main()
    raise SystemExit(0 if good == total else 1)
