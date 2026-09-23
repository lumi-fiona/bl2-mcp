"""The Golden Chest grinder (tickets 19 and 45) - the claims that live on disk.

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

# Ticket 45: the result lies in the chest, laid there with the chest's own loot step's calls.
check("the result is laid in the chest with the loot step's own calls, not thrown out of it",
      "made.GetPickup(True, not step.bDisablePickups)" in src and "pickup.AttachPickupToWorldBody(chest" in src
      and "DropFrom" not in src and "_burst" not in src)
check("nothing is taken until the result lies in the chest",
      src.index("pickup = _mount(") < src.index("_use_up(pc, item)")
      and "if pickup.bIsPickupAttachedToSomething and pickup.Base == chest:" in src)
check("a result waits in the chest: ticket 19's 30 s give-back rule is gone",
      "GIVE_BACK_AFTER" not in src and "now=True" not in src)
check("the grinder never closes the lid over something lying in the chest",
      "if not _holding(chest):" in src)
check("an open chest holding nothing is queued to close when its Opened sequence starts",
      '@hook("WillowGame.WillowInteractiveObject:Behavior_ChangeUsability")' in src
      and "on_usability" in src.split("hooks=[")[-1] and "_closing.append(WeakPointer(chest))\n    return Block" not in src)
check("the prompt reads GRINDER, and the hook that keeps the key price off is registered",
      'PROMPT = "GRINDER"' in src and "on_price" in src.split("hooks=[")[-1])
save_hook = src.split('@hook("WillowGame.WillowPlayerController:SaveGame")')[-1].split("@hook")[0]
check("a save carries a waiting result and leaves it in the chest; only travel hands it over (Lumi)",
      "_carry_into_save(obj)" in save_hook and "_give_back" not in save_hook
      and "on_saved" in src.split("hooks=[")[-1])
check("guns the grinder makes or uses up leave the game by lifespan; Destroy() from Python leaves them",
      ".Destroy()" not in src and "gun.LifeSpan = 0.001" in src)
check("a perfected gun keeps its old name, per character (Lumi)",
      'HiddenSaveOption("Perfected names", {})' in src and "on_weapon_init" in src.split("hooks=[")[-1]
      and "_names[new] = kept or _name_parts(gun.DefinitionData)" in src)

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
