# Community Patch - the claim that needs a map change (AUDIT-RAW/community-patch.md, claim 6)
#
# The counts are proved on disk by community-patch-files.py. What no file can prove is DELIVERY:
# that when a map the patch names loads, its hotfixes are on the game's objects. Since ticket 52
# the game's own hotfix service applies them as the map loads, the way it does for real players,
# and the core reads them back on arrival; this file checks the result on whatever map you are
# standing in, after arriving there.
#
# THE SEQUENCE THE OPERATOR RUNS (nothing here waits, so the waiting is the shell's job):
#
#   1. see what stations exist:
#        echo 'print(sorted(stations()))' | bash bl2-mcp/tools/ask.sh
#   2. go somewhere the patch names (this file lists some if you land badly):
#        echo 'print(travel_to("TundraExpress"))' | bash bl2-mcp/tools/ask.sh
#   3. wait for the load - it takes tens of seconds and the bridge stops answering during it:
#        sleep 20; ASK_TIMEOUT=90 bash bl2-mcp/tools/ask.sh <<< 'print(where())'
#      repeat until the name changes.
#   4. re-send the harness (a map change does not clear it, but a relaunch does):
#        bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#   5. run this file:
#        bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/community-patch-needs-travel.py
reset()

import pathlib
import re

from bl2_modern import core, patchset

controller = pc()
here = where().lower()
mine = [(w, c) for w, c in core._hotfixes if core._kind(w) == "map" and w.lower() == here]
named = sorted({w.lower() for w, _c in core._hotfixes if core._kind(w) == "map"})

check(
    "the game is in a real map, not the menu",
    here not in ("menumap", "loader", "fakeentry"),
    f"the map reads as {here!r}",
)
check(
    "this map is one the patch names hotfixes for",
    bool(mine),
    f"{len(mine)} hotfixes for {here!r}." + ("" if mine else f" Try one of: {named[:12]}"),
)
log = pathlib.Path(core.__file__).parents[2] / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
arrived = re.findall(r"Second Wind: arrived in (\S+);", log.read_text(encoding="utf-8", errors="replace"))
check(
    "the core reported arriving here, so it read this map's hotfixes back",
    bool(arrived) and arrived[-1] == here,
    f"last arrival {arrived[-1] if arrived else None!r}",
)

# In effect, not merely named: a later line on the same property wins and is judged instead.
effect = [c for w, c in core.in_effect(controller, here) if core._kind(w) == "map"]
verdicts = [patchset.check(c) for c in effect]
failed = [(why[:60], c[:100]) for (v, why), c in zip(verdicts, effect) if v == patchset.FAILED]
landed = sum(1 for v, _why in verdicts if v == patchset.LANDED)
check(
    "every one of this map's hotfixes the game applied reads back as asked, and some are here to read",
    landed > 0 and not failed,
    f"{landed} landed, {len(failed)} failed, {len(verdicts) - landed - len(failed)} not loaded "
    f"of {len(effect)} in effect; failed: {failed[:3]}",
)

summary()
