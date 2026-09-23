"""
Borderlands 2 MCP server - drive and inspect the running game from an assistant.

WHY IT EXISTS. Modding this game used to mean: change a line, restart, walk somewhere, click
something, screenshot the result, describe it. Every question cost a person several minutes,
and the answer was usually "no, that guess was wrong too". On 2026-08-19 that loop ate an
evening; roughly half the guesses about how the game worked turned out wrong, and every one of
them was a fact that could simply have been read out of the running game.

This is that loop, deleted. It talks to the `bridge` feature inside the Second Wind mod, which
watches a file, runs whatever Python is in it inside the game, and writes back what came out.

WHAT IT MADE POSSIBLE, on the first evening it existed:
  - the real argument list of the game's item-spawning function (eight, not the two to four
    that had been guessed four separate times)
  - the true mapping between the rarity number an item reports and the loot pool that produces
    it, measured by rolling every pool in the game and recording what came out
  - which of three plausible "give the player an item" calls actually moves the backpack count
  - that the game reports the map as "loader" at the moment a character spawns, which is why
    479 map-specific patch commands had never once run

None of that is in any wiki.

REGISTER IT with Claude Code:

    claude mcp add bl2 -- python "Z:/SteamLibrary/steamapps/common/Borderlands 2/bl2-mcp/server.py"
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

GAME = Path(r"Z:/SteamLibrary/steamapps/common/Borderlands 2")
EXE = GAME / "Binaries" / "Win32" / "Borderlands2.exe"
LOG = GAME / "Binaries" / "Win32" / "Plugins" / "unrealsdk.log"
BRIDGE = GAME / "sdk_mods" / "bl2_modern" / "data" / "bridge"
REQUEST = BRIDGE / "request.py"
RESPONSE = BRIDGE / "response.txt"
HEARTBEAT = BRIDGE / "heartbeat.txt"

mcp = FastMCP("borderlands2")


def _running() -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Borderlands2.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "Borderlands2.exe" in out.stdout


def _press(keys: str) -> None:
    """Send keys to the game window. The only thing here that is not the bridge."""
    subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "$w = New-Object -ComObject wscript.shell; "
            "if ($w.AppActivate('Borderlands 2')) { Start-Sleep -Milliseconds 350; "
            f"$w.SendKeys('{keys}') }}",
        ],
        capture_output=True,
        check=False,
    )


def _run_in_game(code: str, timeout: float = 30.0) -> str:
    """Hand code to the bridge and wait for what it prints."""
    if not _running():
        return "ERROR: the game is not running. Call game_launch first."

    BRIDGE.mkdir(parents=True, exist_ok=True)
    RESPONSE.unlink(missing_ok=True)
    REQUEST.write_text(code, encoding="utf-8")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.4)
        if RESPONSE.is_file():
            try:
                return RESPONSE.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

    beat = HEARTBEAT.read_text(encoding="utf-8").strip() if HEARTBEAT.is_file() else "none"
    return (
        f"ERROR: no answer in {timeout:.0f}s.\n"
        f"bridge heartbeat: {beat}\n"
        "If the heartbeat is missing or stale the game is not at a point where it ticks - "
        "it may be sitting on the press-any-key screen. Try game_launch."
    )


@mcp.tool()
def game_status() -> str:
    """Whether Borderlands 2 is running, and what the mod and the bridge are doing."""
    lines = [f"running: {_running()}"]
    lines.append(f"bridge heartbeat: {HEARTBEAT.read_text(encoding='utf-8').strip() if HEARTBEAT.is_file() else 'none'}")
    if LOG.is_file():
        for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            if "loaded" in line and "core.py" in line:
                lines.append("mod: " + line.split("| ")[-1])
    if _running():
        lines.append(_run_in_game(
            "import unrealsdk\n"
            "pc = unrealsdk.find_all('WillowPlayerController')[-1]\n"
            "print('map:', pc.WorldInfo.GetMapName(False))\n"
            "print('character loaded:', pc.Pawn is not None)\n"
            "print('playthrough:', pc.GetCurrentPlaythrough())\n",
            timeout=15,
        ))
    return "\n".join(lines)


@mcp.tool()
def game_launch(load_character: bool = False, steal_focus: bool = False) -> str:
    """
    Start Borderlands 2.

    IMPORTANT, and the reason the defaults are what they are: getting past the title screen
    and loading a character needs a keypress, and the only way to send one that works on this
    game is to pull its window to the front and type into it. If Lumi is using the machine,
    that types into whatever she is doing and grabs her mouse. It happened once. Do not do it
    to her while she is at the keyboard.

    The good news is that the bridge does NOT need any of that - it comes alive on its own
    about 25 seconds after launch, while the game is still sitting on the title screen, and
    from there every game object, class and function can be read. That covers nearly all
    research and is completely non-disruptive.

    Args:
        load_character: press Continue and wait for a character. STEALS FOCUS. Only with
            steal_focus=True as well, and only when Lumi is away from the machine.
        steal_focus: permission to bring the game to the front and send keys.
    """
    subprocess.run(["taskkill", "/F", "/IM", "Borderlands2.exe"], capture_output=True, check=False)
    time.sleep(2)
    LOG.unlink(missing_ok=True)
    subprocess.Popen(
        [str(EXE), "-NoLauncher", "-nostartupmovies"],
        cwd=str(EXE.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not steal_focus:
        # Wait for the bridge instead of the menu. No keys, no focus, nothing disturbed.
        for _ in range(30):
            time.sleep(3)
            if HEARTBEAT.is_file():
                return (
                    "running, bridge alive, sitting on the title screen.\n"
                    "Every game object and function can be read from here. Loading a character "
                    "would need a keypress, which steals focus - pass steal_focus=True only "
                    "when Lumi is away from the machine."
                )
        return "launched, but the bridge never came alive"

    for i in range(70):
        time.sleep(3)
        if LOG.is_file() and "core.py@" in LOG.read_text(encoding="utf-8", errors="replace"):
            break
        if i >= 4:
            _press(" ")
    else:
        return "the game never reached the main menu"

    time.sleep(6)
    if not load_character:
        return "at the main menu"
    return game_load_character()


@mcp.tool()
def game_load_character() -> str:
    """
    Load the most recent character and wait until the game is really ready.

    STEALS FOCUS - it brings the game to the front and presses Enter. Only use this when Lumi
    is away from the machine; otherwise the keypresses land in whatever she is doing.

    Ready means the backpack can actually be read - the map name alone lies, because the game
    reports a map before its contents exist.
    """
    check = (
        "import unrealsdk\n"
        "pc = unrealsdk.find_all('WillowPlayerController')[-1]\n"
        "try:\n"
        "    n = len(list(pc.GetPawnInventoryManager().Backpack))\n"
        "except Exception:\n"
        "    n = -1\n"
        "print('READY' if (pc.Pawn is not None and n > 0) else 'waiting',"
        " pc.WorldInfo.GetMapName(False), n)\n"
    )
    for _ in range(3):
        _press("{ENTER}")
        for _ in range(20):
            time.sleep(3)
            out = _run_in_game(check, timeout=12).strip().splitlines()
            if out and out[-1].startswith("READY"):
                return out[-1]
    return "could not load a character"


@mcp.tool()
def game_quit() -> str:
    """Close Borderlands 2."""
    subprocess.run(["taskkill", "/F", "/IM", "Borderlands2.exe"], capture_output=True, check=False)
    return "closed"


@mcp.tool()
def game_eval(code: str, timeout: float = 30.0) -> str:
    """
    Run Python inside the running game and return whatever it prints.

    `unrealsdk` is importable, and so is the mod itself - `from bl2_modern.features import
    grinder`. Anything printed comes back. State is kept between calls, so one call can set
    something up and the next can use it.

    Args:
        code: the Python to run. Use print() for anything you want to see.
        timeout: seconds to wait for an answer.
    """
    return _run_in_game(code, timeout=timeout)


@mcp.tool()
def game_find(class_name: str, contains: str = "", limit: int = 40) -> str:
    """
    Find loaded objects of a class, optionally filtered by name.

    Args:
        class_name: an Unreal class, e.g. "ItemPoolDefinition" or "WillowInteractiveObject".
        contains: only objects whose name contains this (case insensitive).
        limit: how many to return.
    """
    code = (
        "import unrealsdk\n"
        f"hits = [o for o in unrealsdk.find_all({class_name!r})\n"
        f"        if {contains!r}.lower() in str(o.Name).lower()]\n"
        f"print(f'{{len(hits)}} found')\n"
        f"for o in hits[:{int(limit)}]:\n"
        "    print('  ', o)\n"
    )
    return _run_in_game(code)


@mcp.tool()
def game_object(path: str, class_name: str = "Object", only: str = "") -> str:
    """
    Read one object's real properties - the ones its class declares, not engine constants.

    Plain dir() on an Unreal object returns hundreds of inherited constants and buries what you
    wanted. This walks the class chain instead and shows only declared properties with values.

    Args:
        path: full object path, e.g. "GD_Itempools.ListDefs.EpicChestGoldenLoot".
        class_name: its class, e.g. "InteractiveObjectLootListDefinition".
        only: show only properties whose name contains this.
    """
    code = (
        "import unrealsdk\n"
        f"o = unrealsdk.find_object({class_name!r}, {path!r})\n"
        "print('object:', o)\n"
        "seen = set()\n"
        "cls = o.Class\n"
        "while cls is not None:\n"
        "    c = cls.Children\n"
        "    while c is not None:\n"
        "        n = str(c.Name)\n"
        "        if 'Property' in str(c.Class.Name) and n not in seen:\n"
        "            seen.add(n)\n"
        f"            if {only!r} and {only!r}.lower() not in n.lower():\n"
        "                c = c.Next; continue\n"
        "            try:\n"
        "                v = str(getattr(o, n))\n"
        "                if v not in ('None', '[]', '0', '0.0', 'False', ''):\n"
        "                    print(f'  {n} = {v[:400]}')\n"
        "            except Exception as e:\n"
        "                print(f'  {n} = <unreadable {e!r}>')\n"
        "        c = c.Next\n"
        "    cls = cls.SuperField\n"
    )
    return _run_in_game(code)


@mcp.tool()
def game_function(class_name: str, function_name: str) -> str:
    """
    Show a game function's real parameter list, in order.

    This is the tool that would have saved the most time: calling an Unreal function with the
    wrong number of arguments fails with an unhelpful error, and guessing costs a round trip
    each time. The item-spawning function takes eight arguments; four separate guesses of two
    to four all failed before anybody simply looked.

    Args:
        class_name: e.g. "ItemPool" or "WillowInventoryManager".
        function_name: e.g. "SpawnBalancedInventoryFromPool".
    """
    # The package has to be part of the path, and which package a class lives in is exactly
    # the kind of thing worth not making the caller remember. Try the ones that exist.
    code = (
        "import unrealsdk\n"
        f"fn = None\n"
        f"for pkg in ('WillowGame', 'Engine', 'GearboxFramework', 'Core', 'GameFramework', ''):\n"
        f"    path = (pkg + '.' if pkg else '') + '{class_name}:{function_name}'\n"
        "    try:\n"
        "        fn = unrealsdk.find_object('Function', path)\n"
        "        break\n"
        "    except Exception:\n"
        "        continue\n"
        "if fn is None:\n"
        f"    print('no function {class_name}:{function_name} in any known package')\n"
        "    raise SystemExit\n"
        "print('function:', fn)\n"
        "c = fn.Children\n"
        "while c is not None:\n"
        "    extra = ''\n"
        "    try:\n"
        "        if c.Struct is not None:\n"
        "            extra = ' -> ' + str(c.Struct.Name)\n"
        "    except Exception:\n"
        "        pass\n"
        "    print(f'   {c.Name:<34} {c.Class.Name}{extra}')\n"
        "    c = c.Next\n"
    )
    return _run_in_game(code)


@mcp.tool()
def game_backpack() -> str:
    """List the player's backpack: kind, rarity, level, name and internal definition."""
    code = (
        "import unrealsdk\n"
        "from bl2_modern.features import grinder as g\n"
        "pc = unrealsdk.find_all('WillowPlayerController')[-1]\n"
        "bp = g._backpack(pc)\n"
        "print(f'{len(bp)} items, ${g._money(pc):,}')\n"
        "print(f\"{'kind':<9} {'rarity':>6} {'lvl':>4}  {'name':<34} definition\")\n"
        "for i in bp:\n"
        "    print(f'{g._kind(i):<9} {g._rarity(i):>6} {g._level(i):>4}  "
        "{g._label(i)[:34]:<34} {g._definition_name(i)}')\n"
    )
    return _run_in_game(code)


@mcp.tool()
def game_log(lines: int = 40, only: str = "") -> str:
    """
    Read the mod's log from the current session.

    Args:
        lines: how many of the last lines to return.
        only: return only lines containing this.
    """
    if not LOG.is_file():
        return "no log yet"
    text = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [
        line.split("| ", 1)[-1]
        for line in text
        if "MISC|" not in line and (not only or only.lower() in line.lower())
    ]
    return "\n".join(kept[-lines:])


@mcp.tool()
def mod_reload_note() -> str:
    """
    Explain how to make edited mod code take effect.

    Worth its own tool because it is the single easiest thing to forget: Python already
    imported inside the game stays imported. Editing a feature file changes nothing until the
    game is restarted, and a test run against stale code looks exactly like a failing fix.
    """
    return (
        "Editing files under sdk_mods/bl2_modern does NOT affect the running game.\n"
        "Call game_launch to restart with the new code.\n"
        "Symptom of forgetting: a fix that provably works still 'fails', or a function you "
        "just added reports as missing."
    )


if __name__ == "__main__":
    mcp.run()
