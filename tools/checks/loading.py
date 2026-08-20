# Every feature loads, every keybind is unique, and nothing is registered twice.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/loading.py
reset()
import bl2_modern, collections, importlib, pkgutil
from bl2_modern import core
from bl2_modern.features import FEATURES

line = core.status_line()
n, _, total = line.split(" - ")[1].split(" ")[0], None, line.split(" of ")[1].split(" ")[0]
check("every feature the pack lists actually loaded", " - ".join(line.split(" - ")[1:]).startswith(f"{total} of {total}"), line)
check("the list has no duplicates", len(FEATURES) == len(set(FEATURES)),
      f"{[k for k, v in collections.Counter(FEATURES).items() if v > 1]}")

binds = [(k.identifier, k.key) for k in bl2_modern.mod.keybinds]
used = collections.Counter(k for _n, k in binds if k)
check("no two keybinds share a key", not [k for k, v in used.items() if v > 1],
      f"{dict(binds)}")

ids = [getattr(o, "identifier", "") for o in bl2_modern.mod.options]
check("no two option pages share a name", len(ids) == len(set(ids)),
      f"{[k for k, v in collections.Counter(ids).items() if v > 1]}")

# a feature file that exists but nobody listed is a feature nobody can turn on
import pathlib
folder = pathlib.Path(bl2_modern.__file__).parent / "features"
on_disk = {f.stem for f in folder.glob("*.py") if f.stem != "__init__"}
unlisted = sorted(on_disk - set(FEATURES))
check("every feature file on disk is either listed or deliberately excluded",
      set(unlisted) <= {"cleanmenu", "fastboot"}, f"unlisted: {unlisted}")
summary()
