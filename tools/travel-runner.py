"""
Run the travel-needing check files that need NO human, unattended, in one sitting.

Each *-needs-travel.py file documents its own operator choreography in its header - travel here,
run me, wait, set STEP, run me again. Until 2026-08-20 a person had to be that operator. This
driver IS that operator, for the files whose choreography a machine can perform: it travels,
waits for the world to actually exist (the map name alone lies - it reports a map before the
map's contents do), sets the STEP globals, and runs each file exactly the way its header says.

What it deliberately does NOT cover, and why - so nobody "fixes" this into covering them:

  * texturefade, display-and-ultrawide, things-on-screen, reward-reroll, alt-use-fast-travel,
    skill-build-slots: their headers demand eyes on the moving picture or a physical key held
    down. Eyes are being added separately (shot.ps1 bursts); a held key cannot be faked - the
    game's own InputKey returns False for injected presses (measured, see cycle.sh header).
  * level-less-gear and what-the-game-would-have-deleted: they need a quit-to-menu and a
    character reload mid-sequence. cycle.sh proves loading WITHOUT keypresses is possible, but
    quitting to the menu unattended is unproven - probe that before adding them here.
  * the-nights-log: wants two minutes of real play, including going down on purpose. Faking
    that from the bridge would test the fake, not the log.
  * difficulty-presets: refuses to arm unless the character is already in playthrough 2.
    Run it by hand once such a character is the loaded one.

Usage, from anywhere:
    python travel-runner.py --list          say what would run, touch nothing
    python travel-runner.py                 run everything below, append to TRAVEL-RESULTS.txt
    python travel-runner.py partner         only files whose name contains "partner"

Every ask goes through ask.sh, which already tells "loading" from "dead" from "crashed".
A crash mid-file is written down, the game is restarted via cycle.sh, and the run continues
with the NEXT file - rerunning the crasher would just hide it in the totals.
"""

import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CHECKS = TOOLS / "checks"
OUT = CHECKS / "TRAVEL-RESULTS.txt"

# The word "bash" alone resolves to Windows' own WSL stub when this script runs under Windows
# Python (measured 2026-08-20: the whole first campaign died on "Windows Subsystem for Linux
# has no installed distributions"). Git's bash is the one every tool here is written for.
BASH = next(
    (p for p in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ) if Path(p).is_file()),
    "bash",
)

# One choreography = the file it runs plus the steps its own header prescribes, in order.
# Step kinds:
#   ("harness",)          load harness.py into the bridge scope
#   ("run", seconds)      send the check file itself, with this ASK_TIMEOUT
#   ("travel", "Name")    harness travel_to() - the name is what the file's header says
#   ("wait",)             poll until a controller, a pawn and a countable backpack all exist
#   ("sleep", seconds)    the header's own prescribed pause
#   ("exec", "code")      one line of Python into the bridge scope (STEP globals, job starts)
#   ("poll_none", "expr", ceiling_s)   re-ask `print(expr)` every 10s until it prints None
#   ("cycle",)            fresh game via cycle.sh - for files that demand an unpolluted session
CHOREOGRAPHY: list[tuple[str, list[tuple]]] = [
    ("game-feel-and-files-needs-travel.py", [
        ("harness",), ("run", 60), ("wait",), ("run", 90),
    ]),
    # STATION NAMES ARE INTERNAL KEYS, measured 2026-08-20 by printing stations() live: there
    # are no spaces ("TundraExpress"), and Three Horns hides behind "IceEast"/"IceWest" while
    # Frostburn Canyon is "IceCanyon". The first campaign's three "stuck" files all died on
    # display names that matched nothing.
    ("save-backup-and-sanity-needs-travel.py", [
        # Its own header: run, then make the game save by fast-travelling, then run again.
        ("harness",), ("run", 60), ("travel", "TundraExpress"), ("wait",),
        ("sleep", 20), ("run", 90),
    ]),
    ("one-key-refill-needs-travel.py", [
        # Step 1 travels itself to Sanctuary and returns immediately. The station drops the
        # character ~3800 units from the machines, and MOVING THE PAWN IS BANNED (see the
        # header - two crashes). The feature's own reach slider goes to 5000, so the test runs
        # at the slider's own maximum instead of walking, and puts the owner's value back.
        ("harness",), ("run", 60), ("wait",),
        ("exec", "from bl2_modern.features import vendorrefill as _trav_V\n"
                 "_trav_prev_reach = _trav_V.reach.value\n"
                 "_trav_V.reach.value = 5000"),
        ("exec", "STEP = 2"), ("run", 90),
        ("exec", "from bl2_modern.features import vendorrefill as _trav_V\n"
                 "_trav_V.reach.value = _trav_prev_reach"),
    ]),
    ("co-op-and-handshake-needs-travel.py", [
        # Run 1 arms, the map must change, run 2 reads and restores.
        ("harness",), ("run", 60), ("sleep", 3), ("travel", "TundraExpress"), ("wait",),
        ("run", 90),
    ]),
    ("community-patch-needs-travel.py", [
        # Needs to ARRIVE in Tundra Express fresh, so bounce out and back in.
        ("harness",), ("travel", "IceEast"), ("wait",),
        ("travel", "TundraExpress"), ("wait",),
        ("harness",), ("run", 60), ("sleep", 2), ("run", 60),
    ]),
    ("core-and-registry-needs-travel.py", [
        ("harness",), ("run", 60), ("travel", "IceCanyon"), ("wait",), ("run", 90),
    ]),
    ("extras-and-scaling-needs-travel.py", [
        # Six phases with minute-long waits; phases 4 and 5 price a death by killing the
        # character on purpose (money measured and refunded, no gear lost - its own header).
        # The trip plan is seeded BEFORE phase 0 - the file respects an existing SCALE_TRIP -
        # because its own 'ice_' default matches no real station key.
        ("harness",),
        ("exec", 'SCALE_TRIP = {"phase": 0, "there": "IceEast", "home": "Sanctuary"}'),
        ("run", 90), ("sleep", 60), ("run", 90), ("sleep", 60), ("run", 90),
        ("sleep", 60), ("run", 90), ("run", 90), ("sleep", 40), ("run", 90),
    ]),
    ("measure-the-game-needs-travel.py", [
        # The call shape is the one the file's own header prescribes, module and all.
        ("harness",), ("exec", "from bl2_modern import reportjob\n"
                               "from bl2_modern.features import patchproof as F\n"
                               "reportjob.start(F.OWNER, F.NAME, F._work, 6)"),
        ("poll_none", "reportjob.busy()", 600), ("run", 90),
    ]),
    ("what-the-game-would-have-deleted-needs-travel.py", [
        # Its header wants: run, save-and-quit to the menu, load the SAME character back, run
        # again. The bridge scope lives in the PROCESS, not the map, so quitting to the menu
        # keeps run 1's state alive - a full restart would lose it. Both menu primitives are
        # the ones cycle.sh already proved work without a keypress.
        ("harness",), ("run", 90), ("menu",), ("load_character",), ("wait",),
        ("harness",), ("run", 90),
    ]),
    ("extra-loot-roll-per-player-needs-travel.py", [
        # Demands a fresh game and a map with at least two living enemies, not Sanctuary.
        ("cycle",), ("harness",), ("travel", "Lynchwood"), ("sleep", 60), ("wait",), ("run", 90),
    ]),
    ("partner-aimed-loot-needs-travel.py", [
        ("cycle",), ("harness",), ("travel", "Lynchwood"), ("sleep", 60), ("wait",), ("run", 90),
    ]),
]

# Every name this probe binds is _trav_-prefixed ON PURPOSE: the bridge keeps ONE scope alive
# for the whole session, and the first version of this probe bound a bare `pc`, shadowing the
# harness's pc() FUNCTION with a raw object - the very next check file then died on
# "'UObject' object is not callable" (measured 2026-08-20, first shakedown run).
READY_PROBE = """
import unrealsdk
_trav_pcs = [o for o in unrealsdk.find_all("WillowPlayerController") if not o.Name.startswith("Default__")]
_trav_pc = _trav_pcs[-1] if _trav_pcs else None
try:
    _trav_n = len(list(_trav_pc.GetPawnInventoryManager().Backpack))
except Exception:
    _trav_n = -1
print("READY" if (_trav_pc and _trav_pc.Pawn is not None and _trav_n >= 0) else "waiting")
"""


def ask(code: str | None, path: Path | None = None, timeout: int = 40) -> tuple[int, str]:
    """One request into the game. Returns ask.sh's exit code and everything it printed."""
    cmd = [BASH, str(TOOLS / "ask.sh")] + ([str(path)] if path else [])
    r = subprocess.run(
        cmd, input=None if path else code, capture_output=True, text=True,
        env={**__import__("os").environ, "ASK_TIMEOUT": str(timeout)},
        timeout=timeout + 30,
    )
    return r.returncode, (r.stdout + r.stderr)


def wait_ready(ceiling_s: int = 240) -> bool:
    """The world exists when a pawn and a countable backpack do - cycle.sh's own measure."""
    deadline = time.time() + ceiling_s
    while time.time() < deadline:
        time.sleep(5)
        rc, out = ask(READY_PROBE, timeout=25)
        if rc == 0 and "READY" in out:
            return True
    return False


def crashed() -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(TOOLS / "crashwatch.ps1")],
        capture_output=True, text=True, timeout=60,
    )
    return r.stdout if "crashdialog" in r.stdout else ""


def cycle() -> bool:
    r = subprocess.run([BASH, str(TOOLS / "cycle.sh")], capture_output=True, text=True,
                       timeout=600)
    return r.returncode == 0


def log(line: str) -> None:
    print(line, flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_file(name: str, steps: list[tuple]) -> str:
    """Returns 'ok', 'crashed', or 'stuck'. Detail lands in TRAVEL-RESULTS.txt either way."""
    path = CHECKS / name
    log(f"##### {name.removesuffix('.py')} #####")
    for step in steps:
        kind = step[0]
        if kind == "harness":
            ask(None, path=TOOLS / "harness.py", timeout=60)
        elif kind == "run":
            rc, out = ask(None, path=path, timeout=step[1])
            log(out.rstrip())
            if rc == 4:
                return "crashed"
            if rc in (2, 3):
                return "stuck"
            # ask.sh exits 0 for a request that raised - the traceback IS the answer. It is
            # not an ok run of the check, though, and the summary must say so.
            if "--- it raised ---" in out or "did not run to the end" in out:
                return "raised"
        elif kind == "travel":
            # travel_to() wants the station's EXACT key, and station names are not always the
            # map's display name (measured: Sanctuary's station is not literally "Sanctuary").
            # So match the way a person would - exact first, then substring - and say loudly
            # when nothing matches instead of raising into a lost response.
            rc, out = ask(
                f'_trav_t = "{step[1]}"\n'
                "_trav_found = stations()\n"
                "_trav_want = _trav_t.replace(' ', '').lower()\n"
                "_trav_key = _trav_t if _trav_t in _trav_found else next((_n for _n in _trav_found if _trav_want in _n.replace(' ', '').lower()), None)\n"
                'print(travel_to(_trav_key) if _trav_key else "NO STATION for " + _trav_t + ": " + str(sorted(_trav_found)[:12]))',
                timeout=40,
            )
            if "NO STATION" in out:
                log(f"!!! travel failed: {out.strip()}")
                return "stuck"
        elif kind == "wait":
            if not wait_ready():
                return "stuck"
        elif kind == "sleep":
            time.sleep(step[1])
        elif kind == "exec":
            ask(step[1] + "\nprint('set')", timeout=30)
        # There is deliberately NO step that moves the pawn. Writing Pawn.Location (via
        # make_struct - a tuple does not even assign) moved the character, and the game then
        # died with a fatal error inside the audio engine's memory manager within minutes,
        # TWICE on 2026-08-20 - once on a process that had run for an hour and once on a
        # process one map old, so it was the teleport and not memory pressure. The audio
        # engine tracks the player's position; teleporting by force-feeding the position
        # appears to be something it cannot survive. Tests that need the character somewhere
        # specific either use a feature's own range option, or go on the hands-on list.
        elif kind == "poll_none":
            expr, ceiling = step[1], step[2]
            deadline = time.time() + ceiling
            while time.time() < deadline:
                rc, out = ask(f"print({expr})", timeout=30)
                if "None" in out:
                    break
                time.sleep(10)
            else:
                log(f"!!! {expr} never returned None within {ceiling}s")
                return "stuck"
        elif kind == "cycle":
            if not cycle():
                return "stuck"
        elif kind == "menu":
            # Save-and-quit to the main menu. The game saves on the way out by itself.
            ask('pc().ConsoleCommand("disconnect")\nprint("disconnecting")', timeout=20)
            deadline = time.time() + 120
            at_menu = False
            while time.time() < deadline:
                time.sleep(4)
                rc, out = ask(
                    "import unrealsdk\n"
                    '_trav_fe = [o for o in unrealsdk.find_all("FrontendGFxMovie") if not o.Name.startswith("Default__")]\n'
                    'print("MENU" if _trav_fe else "waiting")',
                    timeout=20,
                )
                if "MENU" in out:
                    at_menu = True
                    break
            if not at_menu:
                log("!!! never reached the main menu after disconnect")
                return "stuck"
        elif kind == "load_character":
            # cycle.sh's own two calls, verbatim: cache the last save, then launch it.
            ask(
                "import unrealsdk\n"
                '_trav_pcs = [o for o in unrealsdk.find_all("WillowPlayerController") if not o.Name.startswith("Default__")]\n'
                "_trav_pcs[-1].LoadLastSavedSaveGame()\n"
                'print("cached:", _trav_pcs[-1].HasCachedSaveGame())',
                timeout=30,
            )
            time.sleep(3)
            ask(
                "import unrealsdk\n"
                '_trav_fe = [o for o in unrealsdk.find_all("FrontendGFxMovie") if not o.Name.startswith("Default__")][0]\n'
                "_trav_fe.LaunchSaveGame(0)\n"
                'print("launched")',
                timeout=30,
            )
    if crashed():
        return "crashed"
    return "ok"


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else ""
    if "--list" in sys.argv:
        for name, steps in CHOREOGRAPHY:
            if only and only not in name:
                continue
            print(f"{name}: {' -> '.join(s[0] + (f'({s[1]})' if len(s) > 1 else '') for s in steps)}")
        return

    results: dict[str, str] = {}
    for name, steps in CHOREOGRAPHY:
        if only and only not in name:
            continue
        outcome = run_file(name, steps)
        results[name] = outcome
        if outcome == "crashed":
            log(f"*** {name} CRASHED THE GAME - restarting and moving on ***")
            if not cycle():
                log("*** restart failed, stopping the run here ***")
                break
        elif outcome == "stuck":
            log(f"*** {name} got stuck (no crash, no answer) - restarting to be safe ***")
            if not cycle():
                log("*** restart failed, stopping the run here ***")
                break

    log("\n=== TRAVEL RUN SUMMARY ===")
    for name, outcome in results.items():
        log(f"{outcome:8} {name}")
    log(f"full output in {OUT}")


if __name__ == "__main__":
    main()
