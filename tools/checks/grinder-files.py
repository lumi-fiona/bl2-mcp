"""The Golden Chest grinder (ticket 19) - the claims that live on disk.

Ordinary Python, outside the game:

    python "bl2-mcp/tools/checks/grinder-files.py"

The old grinder.py and levelless.py were retired to features/retired/, which nothing loads.
Everything that borrowed from them now borrows from the new grinder.py or the harness.
"""

import ast
import re
from pathlib import Path

RESULTS: list = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok, str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / "sdk_mods" / "bl2_modern"
FEATURES = PACK / "features"
GRINDER = FEATURES / "grinder.py"
TOOLS = ROOT / "bl2-mcp" / "tools"


def read(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


src = read(GRINDER)
tree = ast.parse(src)
defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
listed = ast.literal_eval(re.search(r"FEATURES = (\[.*?\])", read(FEATURES / "__init__.py"), re.S).group(1))

check("the pack loads the new grinder and no longer loads levelless",
      "grinder" in listed and "levelless" not in listed, f"{len(listed)} features")
check("the old grinder and levelless are kept, retired, where nothing loads them",
      (FEATURES / "retired" / "grinder.py").exists() and (FEATURES / "retired" / "levelless.py").exists()
      and not (FEATURES / "levelless.py").exists() and "retired" not in listed)

live = [p for p in PACK.rglob("*.py") if "retired" not in p.parts and "__pycache__" not in p.parts]
old_imports = [f"{p.name}:{i + 1}" for p in live for i, line in enumerate(read(p).splitlines())
               if re.search(r"import levelless|\.levelless import|features\.retired|from \.retired", line)]
check("no live pack file imports the retired modules", not old_imports, f"{old_imports}")
needs = {"itemcheck.py": "from .grinder import carried", "bestpart.py": "grinder.carried(pc)",
         "museum.py": "grinder._relevel_one(item, int(level))"}
check("itemcheck, bestpart and museum borrow from the new grinder, which has what they use",
      all(line in read(FEATURES / f) for f, line in needs.items()) and {"carried", "_relevel_one"} <= defined)

check("no key opens the grinder (ticket 15 dropped key H)", "keybind" not in src)
check("the per-character list keeps the old name, so a gun marked before stays level-less",
      'HiddenSaveOption("Level-less items", [])' in src)
check("the chest's menu offers exactly the two tools",
      '"Make a gun level-less"' in src and '"Perfect a gun"' in src
      and not any(w in src for w in ('"Grind for', '"Report what', '"Open the chest normally"')))
check("a relevel resets a gun's attributes first (each re-init adds to some, measured)",
      "_fresh_attributes(item)" in src and "item.InitializeFromDefinitionData" in src)
check("using up an item refreshes the backpack's own count", "UpdateBackpackInventoryCount()" in src)
check("a result on the floor goes along when you travel, not only when you save",
      '@hook("WillowGame.WillowGameInfo:TravelToStation")' in src and "on_travel" in src.split("hooks=[")[-1])

checks = [p for p in (TOOLS / "checks").glob("*.py") if p.name != Path(__file__).name]
borrowed = [p.name for p in checks + [TOOLS / "harness.py", ROOT / "bl2-mcp" / "server.py"]
            if re.search(r"features import levelless|features\.levelless|G\.POOLS|G\._spawn_from_pool|"
                         r"g\._backpack|g\._kind", read(p))]
check("no check, the harness or the MCP server still borrows the old grinder's helpers",
      not borrowed, f"{borrowed}")
check("the harness carries the loot pools those checks borrowed",
      "POOLS = {" in read(TOOLS / "harness.py") and "def spawn_from_pool" in read(TOOLS / "harness.py"))

good = sum(1 for _, ok, _ in RESULTS if ok)
print(f"\n{good}/{len(RESULTS)} passed")
for name, ok, detail in RESULTS:
    if not ok:
        print(f"   FAILED: {name}  {detail}")
