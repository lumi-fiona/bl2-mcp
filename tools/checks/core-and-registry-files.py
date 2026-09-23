"""
Core, feature registry and developer bridge - the claims that live on disk.

    python bl2-mcp/tools/checks/core-and-registry-files.py

Ordinary Python, outside the game. It reads three things and writes nothing:

  * the pack's own source, for the claims about what is in the feature list
  * Binaries/Win32/Plugins/unrealsdk.log, which is deleted on every launch, so everything
    it says is about the most recent launch and nothing else
  * data/bridge/heartbeat.txt, sampled for a few seconds to see it move

Covers, from AUDIT-RAW/: feature-registry-list.md claims 1-4; core-registry-...md claims
4, 5, 6, 10 and the double-status-line and one-shot-map-name bugs; developer-bridge.md
claims 3, 7, 8, 12 and the _ready race.
"""

import ast
import re
import sys
import time
from datetime import datetime
from pathlib import Path

GAME = Path(r"Z:/SteamLibrary/steamapps/common/Borderlands 2")
PACK = GAME / "sdk_mods" / "bl2_modern"
LOG = GAME / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
BRIDGE_DIR = PACK / "data" / "bridge"
HEARTBEAT = BRIDGE_DIR / "heartbeat.txt"

# How long to watch the heartbeat move. The claim under test is "roughly every three
# seconds", so the window has to be long enough to hold several of them.
SAMPLE_SECONDS = 18.0

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok, str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    return ok


def summary():
    good = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{good}/{len(RESULTS)} passed")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"   FAILED: {name}  {detail}")
    return good, len(RESULTS)


def stamp(line):
    """The datetime at the start of an unrealsdk.log line, or None."""
    try:
        return datetime.strptime(line[:24], "%Y-%m-%d %H:%M:%S.%fZ")
    except ValueError:
        return None


# --- the feature list, against the files next to it -------------------------------------


def check_registry():
    init = PACK / "features" / "__init__.py"
    namespace = {}
    exec(compile(init.read_text(encoding="utf-8"), str(init), "exec"), namespace)  # noqa: S102
    features = namespace["FEATURES"]

    check(
        "savebackup is the first name in the feature list, so every later feature runs on a backed-up machine",
        features[0] == "savebackup",
        f"list starts {features[:3]}",
    )
    check(
        "every name in the feature list is a file that exists",
        all((PACK / "features" / f"{name}.py").is_file() for name in features),
        f"missing: {[n for n in features if not (PACK / 'features' / f'{n}.py').is_file()]}",
    )
    check(
        "no name appears in the feature list twice",
        len(set(features)) == len(features),
        f"{len(features)} names, {len(set(features))} distinct",
    )
    # The pinned pair. "15 of 15 loaded" counts the list against itself, so a feature file
    # that nobody added to the list is invisible in the log - this is the only thing that
    # says so. cleanmenu and fastboot are the two deliberate exclusions, and the comment at
    # features/__init__.py:12-20 gives the reason.
    orphans = {
        p.stem for p in (PACK / "features").glob("*.py")
    } - set(features) - {"__init__"}
    check(
        "the only feature files left out of the list are the two that were left out on purpose",
        orphans == {"cleanmenu", "fastboot"},
        f"left out: {sorted(orphans)}",
    )
    check(
        "and the reason they are left out is written down next to the list",
        "cleanmenu" in init.read_text(encoding="utf-8").split("FEATURES")[0],
        "the comment above FEATURES names them",
    )


# --- the bridge's source ----------------------------------------------------------------


def check_bridge_source():
    text = (PACK / "features" / "bridge.py").read_text(encoding="utf-8")

    # Matching the word anywhere in the file is no good: the docstring says "requests" a dozen
    # times and "no network, no port, nothing listening" once. What matters is what it imports.
    imported = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    networking = {
        "socket", "socketserver", "http", "urllib", "requests", "asyncio", "ssl",
        "ftplib", "smtplib", "telnetlib", "xmlrpc", "flask", "websocket", "websockets",
    }
    check(
        "nothing in the bridge can listen on the network - it imports nothing that could",
        not (imported & networking),
        f"imports {sorted(imported)}",
    )
    lines = text.splitlines()
    unlink = next((i for i, line in enumerate(lines) if "REQUEST.unlink()" in line), -1)
    run = next((i for i, line in enumerate(lines) if "exec(code, _scope)" in line), -1)
    check(
        "the request file is deleted before it is run, so a request that crashes the game is not replayed on the next launch",
        0 <= unlink < run,
        f"unlink at line {unlink + 1}, exec at line {run + 1}",
    )
    check(
        "the answer is written to a temporary file and moved into place, so nothing can read half of it",
        ".part" in text and "temporary.replace(RESPONSE)" in text,
        "bridge.py:75-77",
    )
    check(
        "no half-written answer is sitting on disk right now",
        not (BRIDGE_DIR / "response.part").exists(),
        f"{BRIDGE_DIR / 'response.part'}",
    )
    # Two Borderlands2.exe processes were seen live on 2026-08-19. They share this one folder
    # and there is nothing in the heartbeat to tell them apart.
    check(
        "the heartbeat still carries no process id, so two running games are indistinguishable from outside",
        "getpid" not in text,
        "bug pin: os.getpid() in the heartbeat line would make the condition visible",
    )
    # Bug pins, all three of them passing while the bug is there. Named so that the day someone
    # fixes one, the check goes red and says which promise just changed.
    check(
        "only what a request prints to stdout comes back - anything logged with unrealsdk.logging still does not",
        "redirect_stderr" not in text,
        "bug pin: contextlib.redirect_stderr alongside redirect_stdout is the one-line half-fix",
    )
    check(
        "a request that raises SystemExit still escapes into the tick hook, because the guard catches Exception and not BaseException",
        "except BaseException" not in text,
        "bug pin: bridge.py:103, where the comment promises a failed request can never take the game down",
    )
    check(
        "switching the developer bridge off still does not stop it writing to disk, because _ready never looks at the switch",
        "def _ready" in text
        and "enabled" not in text.split("def _ready")[1].split("register(")[0],
        "bug pin: bridge.py:141-148 - developer-bridge.md claim 11 is expected to fail for this reason",
    )


# --- what the last launch wrote to the log ------------------------------------------------


def check_callers():
    """The two things that write request.py, and the two that decide the game is up."""
    ask = (GAME / "bl2-mcp" / "tools" / "ask.sh").read_text(encoding="utf-8")
    server = (GAME / "bl2-mcp" / "server.py").read_text(encoding="utf-8")
    cycle = (GAME / "bl2-mcp" / "tools" / "cycle.sh").read_text(encoding="utf-8")

    # The audit says "no caller writes the request atomically". That is now only half true:
    # ask.sh writes request.py.part and moves it into place. server.py still does not.
    check(
        "ask.sh writes the request to a temporary name and moves it, so the bridge cannot run half a script",
        "request.py.part" in ask and re.search(r"mv .*request\.py\.part", ask) is not None,
        "the bridge treats request.py.is_file() as 'complete', and open(...,'w') makes that true "
        "before a byte is written",
    )
    check(
        "the MCP server writes the request in one plain call, so it can still be caught half-written",
        "REQUEST.write_text(code" in server,
        "bug pin: server.py:80 - the same .part-then-replace trick fixes it",
    )
    check(
        "cycle.sh deletes the old heartbeat before waiting for a new one",
        re.search(r"rm -f .*heartbeat\.txt", cycle) is not None,
        "otherwise a heartbeat from any previous run reads as 'the bridge is up' immediately",
    )
    check(
        "game_launch still does not, so on this machine it calls the bridge alive about four minutes early",
        "HEARTBEAT.unlink" not in server and "LOG.unlink" in server,
        "bug pin: server.py:144 deletes the SDK log and leaves the heartbeat behind",
    )


def check_log():
    if not LOG.is_file():
        check("the SDK log from the last launch is on disk", False, f"no {LOG}")
        return
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()

    status = [line for line in lines if re.search(r"Second Wind \S+ - \d+ of \d+ loaded", line)]
    # "probe" is not a feature this pack ships - it is the one name community-patch.py:64-70
    # gives a throwaway Feature so it can drive _run_one_patch directly, exercising the exact
    # code path a real feature would without duplicating its logic. That logs through the same
    # generic line a real bundled-patch feature does, so a log with several test runs behind it
    # can carry several "Second Wind: probe applied, ..." lines that have nothing to do with
    # what the pack itself shipped. Excluded so this measures the pack's own footprint, not the
    # check suite's.
    applied = [
        line
        for line in lines
        if "commands run," in line
        and "Second Wind:" in line
        and "Second Wind: probe applied" not in line
    ]
    per_map = [
        re.search(r"Second Wind: (\d+) commands for (\S+) applied, (\d+) failed", line)
        for line in lines
    ]
    per_map = [m for m in per_map if m]
    named = [line for line in lines if "the game calls this map" in line]
    reapplied = [
        re.search(r"re-applied (\d+) hotfix commands on level load, (\d+) failed", line)
        for line in lines
    ]
    reapplied = [m for m in reapplied if m]
    watching = [line for line in lines if "bridge: watching" in line]

    check(
        "the last thing the pack said about loading is that every feature loaded, with none named as failed",
        bool(status)
        and re.search(r"(\d+) of (\d+) loaded", status[-1]).group(1)
        == re.search(r"(\d+) of (\d+) loaded", status[-1]).group(2)
        and "FAILED" not in status[-1],
        status[-1].split("INFO| ")[-1] if status else "no status line at all",
    )
    # The cosmetic bug, made visible: the same sentence is printed twice per launch, minutes
    # apart, from two different files, and only the second one can ever mention an apply
    # failure. Anyone grepping gets two hits and no way to tell which is authoritative.
    # The FILE is the anchor, never the line number: pinning core.py@468 made every ordinary
    # edit above that line a false failure here (it fired 2026-08-20 when a save-id migration
    # was added). What matters is which file speaks, and in which order.
    check(
        "that same sentence is printed twice per launch, from two different files",
        len(status) == 2
        and "__init__.py@" in status[0]
        and "core.py@" in status[1],
        f"{len(status)} status lines"
        + (
            f", {(stamp(status[1]) - stamp(status[0])).total_seconds():.0f}s apart"
            if len(status) == 2 and stamp(status[0]) and stamp(status[1])
            else ""
        ),
    )

    # Not "two lines": whether a feature's patch runs at all is a switch the player owns, and a
    # feature that is switched off says so instead. What must hold either way is that each one
    # speaks exactly once per launch - apply runs again on every character load, and a second
    # line here would mean the whole patch had been applied twice.
    # Same "probe" exclusion as `applied` above - community-patch.py's throwaway Feature logs
    # this exact line too when it drives a config with the master switch off.
    off = [
        name
        for name in re.findall(
            r"Second Wind: (.+?) is switched off, running nothing", "\n".join(lines),
        )
        if name != "probe"
    ]
    spoke = [re.search(r"Second Wind: (.+?) applied", line).group(1) for line in applied] + off
    check(
        "each feature with a bundled patch file spoke exactly once, even though apply runs again on every character load",
        bool(spoke) and len(set(spoke)) == len(spoke),
        f"applied: {[re.search(r'Second Wind: (.+?) applied', line).group(1) for line in applied]}"
        + (f", switched off: {off}" if off else ""),
    )

    numbers = [
        re.search(
            r"Second Wind: (.+?) applied, (\d+) commands run, (\d+) failed, (\d+) of them "
            r"repeating on each level load, (\d+) held for particular maps, (\d+) lines ignored",
            line,
        )
        for line in applied
    ]
    numbers = [m for m in numbers if m]
    check(
        "the number of commands actually run is logged, so a patch that silently does nothing would be visible",
        bool(numbers) and all(int(m.group(2)) > 0 for m in numbers),
        ", ".join(f"{m.group(1)}: {m.group(2)} run" for m in numbers),
    )
    check(
        "not one patch command was refused, which is also why the one-bad-line-cannot-stop-the-rest branch has never run for real",
        bool(numbers) and all(int(m.group(3)) == 0 for m in numbers),
        ", ".join(f"{m.group(1)}: {m.group(3)} failed" for m in numbers)
        + " - the in-game file exercises that branch against a stand-in controller",
    )
    # The audit asks for "483 keys in _by_level (479 + 4)". Both halves are wrong: 483 counts
    # commands, not maps, and the figure moves the moment a patch section is unticked - with the
    # Community Patch switched off it is 4. So what is checked here is that the numbers add up
    # inside each line; the in-game file compares them against what the core is still holding.
    check(
        "every patch line's own numbers add up: the commands kept for later are a subset of the ones it tried",
        bool(numbers)
        and all(int(m.group(4)) <= int(m.group(2)) + int(m.group(3)) for m in numbers),
        ", ".join(
            f"{m.group(1)}: {m.group(2)} run, {m.group(4)} of them repeating, "
            f"{m.group(5)} held for particular maps"
            for m in numbers
        ),
    )

    # Claim 4 wanted the patch line compared against a FrontendGFxMovie line. There is no such
    # line in the log - the SDK does not log hooks firing - so what is checkable is the order
    # against the pack's own two status lines: importing happens minutes before the menu, and
    # the patch runs between the import and the ready report.
    if len(status) == 2 and applied:
        first, last = stamp(status[0]), stamp(status[1])
        patch_at = stamp(applied[0])
        check(
            "the patch ran long after the pack imported and just before it reported itself ready",
            None not in (first, last, patch_at)
            and first < patch_at <= last
            and (patch_at - first).total_seconds() > 10,
            f"{(patch_at - first).total_seconds():.0f}s after importing, "
            f"{(last - patch_at).total_seconds():.1f}s before the ready line",
        )

    check(
        "the hotfix commands were re-run on a level load",
        bool(reapplied) and all(int(m.group(1)) > 0 for m in reapplied),
        ", ".join(f"{m.group(1)} commands, {m.group(2)} failed" for m in reapplied[:3]),
    )
    # The audit files this as needing a character walked through a fast-travel station. The log
    # from the last launch already has it: the map watcher fired on arrival at real maps.
    check(
        "map-specific commands ran when their map loaded, at least once, with a non-zero count",
        bool(per_map) and any(int(m.group(1)) > 0 for m in per_map),
        ", ".join(f"{m.group(1)} for {m.group(2)}" for m in per_map[:5])
        or (
            "no arrivals logged"
            + (
                f" - and {off} ran nothing this launch, so almost no map has commands waiting"
                if off
                else " - travel somewhere the patch names and re-read the log"
            )
        ),
    )
    # The one-shot bug, visible in the log: the diagnostic that exists to make a map-name
    # mismatch loud is allowed to fire once per process, and the menu map is always first.
    check(
        "the map-name report fired exactly once this launch, and it was about the main menu",
        len(named) == 1 and "menumap" in named[0],
        (named[0].split("INFO| ")[-1] if named else "it never fired at all")
        + f"  ({len(per_map)} maps arrived at since)",
    )

    # The _ready race: apply_all runs on every character load, and the bridge's apply deletes
    # request.py and overwrites response.txt. One line per launch means no character was loaded.
    check(
        "the bridge re-prepared its folder more than once, which is it deleting whatever request was in flight",
        len(watching) > 1,
        f"{len(watching)} 'bridge: watching' lines"
        + (" - only one, so no character was loaded this launch" if len(watching) == 1 else ""),
    )

    # Per-character settings are keyed by mod id, and the id this pack used to save under is
    # gone. Every character's difficulty preset and level-less marks saved under the old name
    # are orphaned, and this one WARN line is the only thing that says so.
    orphaned = [line for line in lines if "unregistered mod" in line]
    check(
        "no character is carrying settings saved under a mod id the pack no longer answers to",
        not orphaned,
        orphaned[0].split("WARN| ")[-1]
        + " - renaming the mod abandoned them silently; a migration or a visible note is owed"
        if orphaned
        else "none - core.py now also answers to the old id (_adopt_old_save_id), so any "
        "settings still filed under it are adopted instead of dropped",
    )


# --- the heartbeat, watched for a few seconds ----------------------------------------------


def check_heartbeat():
    if not HEARTBEAT.is_file():
        check(
            "the bridge is writing a heartbeat, so 'is the game running this' is answerable without sending a request",
            False,
            f"no {HEARTBEAT} - the game is not running, or the bridge is switched off",
        )
        return

    first = HEARTBEAT.read_text(encoding="utf-8", errors="replace").strip()
    shape = re.match(r"alive, (\d+) ticks, (\d+) requests served$", first)
    check(
        "the heartbeat says how many ticks and how many requests, in the shape the callers parse",
        bool(shape),
        first,
    )

    changes = []
    last_text = first
    last_change = time.monotonic()
    started = last_change
    while time.monotonic() - started < SAMPLE_SECONDS:
        time.sleep(0.25)
        try:
            now = HEARTBEAT.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if now != last_text:
            moment = time.monotonic()
            changes.append(moment - last_change)
            last_change = moment
            last_text = now

    final = re.match(r"alive, (\d+) ticks", last_text)
    # The bridge only ticks inside PlayerTick, which stops dead during a level load. A frozen
    # heartbeat here means loading, a hung frame, or a dead game - and from outside those look
    # identical, which is itself one of the bugs on the list.
    check(
        "the heartbeat ticks up on its own while nothing is asking it anything",
        bool(shape and final) and int(final.group(1)) > int(shape.group(1)),
        f"{shape.group(1) if shape else '?'} -> {final.group(1) if final else '?'} ticks "
        f"in {SAMPLE_SECONDS:.0f}s"
        + (
            " - it did not move at all, which is a loading screen, a hung frame or a dead game; "
            "re-run once the map has settled"
            if shape and final and int(final.group(1)) == int(shape.group(1))
            else ""
        ),
    )
    # bridge.py:127 says "Roughly every three seconds". Measured 2026-08-19 it was ~9.7s.
    # Measured again 2026-08-20 with nothing else touching the bridge (this file does not send
    # requests, it only reads a text file), the gaps were 2.0s then 12.8s - so it is not the
    # check suite crowding it either, it is bridge.py's own comment that is wrong. The machine
    # runs at ~92-100 ticks a second, not the 264 assumed at bridge.py:58-61: 900 ticks between
    # writes at ~100 a second is ~9s, not 3, and real frame time is not perfectly steady on top
    # of that. Every timing decision downstream (ask.sh's poll interval, server.py's staleness
    # message) trusts the three, so this is a real bug pin, not a test artefact - it asserts
    # the measured behaviour instead of the stale claim. 20s is not a measurement, it is a line
    # comfortably above the worst gap seen so far (12.8s) and comfortably below "the heartbeat
    # has actually stopped".
    check(
        'the heartbeat\'s gaps stay well short of "stalled", even though bridge.py:127\'s '
        '"roughly three seconds" is measured wrong on this machine',
        bool(changes) and max(changes) < 20.0,
        f"gaps: {[f'{g:.1f}s' for g in changes]}" if changes else "it never changed at all",
    )


if __name__ == "__main__":
    check_registry()
    check_bridge_source()
    check_callers()
    check_log()
    check_heartbeat()
    good, total = summary()
    sys.exit(0 if good == total else 1)
