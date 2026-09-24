# Core arrivals - the claims that need a map change (tickets 05 and 52): one arrival per map load,
# reported with the real map name, and the pack's hotfixes still in the game's own hotfix service
# after the travel.
#
# It is one file run TWICE, either side of a fast travel. The first run leaves a baseline in the
# bridge's scope; the second compares against it and then refreshes the baseline, so you can
# travel and re-run as many times as you like.
#
# THE SEQUENCE, from the shell - never poll from inside a request, because the map change needs
# the very frame a loop would be holding:
#
#   1. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/core-and-registry-needs-travel.py
#   2. echo 'travel_to("IceCanyon")' | bash bl2-mcp/tools/ask.sh
#   3. sleep 20; then poll from the shell until where() changes
#   4. bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/core-and-registry-needs-travel.py

import pathlib
import re

from bl2_modern import core

_log = pathlib.Path(core.__file__).parents[2] / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
_service = core._hotfix_service()
_keys = core._entries[0] if core._entries else []
_now = {
    "map": where().lower(),
    "arrivals": re.findall(r"Second Wind: arrived in (\S+);", _log.read_text(encoding="utf-8", errors="replace")),
    "hotfixes": len(core._hotfixes),
    "service": None if _service is None else len(_service.Keys),
    "ours": bool(_keys) and _service is not None and _keys[0] in _service.Keys,
}

if "CORE_TRAVEL_BASELINE" not in globals():
    CORE_TRAVEL_BASELINE = _now
    print(f"baseline taken in {_now['map']}: {len(_now['arrivals'])} arrivals logged so far")
    print("fast travel station names:")
    print(sorted(stations()))
    print("now travel, wait for where() to change, and run this file again.")
else:
    reset()
    _was = CORE_TRAVEL_BASELINE
    _new = _now["arrivals"][len(_was["arrivals"]):]
    check(
        "the map really did change between the two runs",
        _now["map"] != _was["map"],
        f"{_was['map']} -> {_now['map']}",
    )
    check(
        "the travel was reported as exactly one arrival, in the map the game names",
        _new == [_now["map"]],
        f"arrivals since the baseline: {_new}",
    )
    check(
        "the pack's hotfixes are still in the game's hotfix service after the travel",
        _now["ours"] and _now["service"] == _was["service"],
        f"service keys {_was['service']} -> {_now['service']}, the pack's there: {_now['ours']}",
    )
    check(
        "arriving did not add to the pack's hotfixes",
        _now["hotfixes"] == _was["hotfixes"],
        f"{_was['hotfixes']} -> {_now['hotfixes']}",
    )
    CORE_TRAVEL_BASELINE = _now
    summary()
    print("\nbaseline refreshed - travel again and re-run to check another arrival.")
