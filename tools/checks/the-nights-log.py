# The night's log - everything decidable without an enemy, a second player or a reload.
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/harness.py
#      bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/the-nights-log.py
#
# Nothing here kills anything or waits for anything. Every hook body is called directly with
# stand-in arguments, and the file writing is pointed at a scratch folder so the real logs are
# never touched - which also means the pruning check can delete things without being frightening.
#
# The checks that matter most are the first block: whether the five unreal functions this feature
# guessed at actually exist. Every one of them came from reading another mod's source or the
# game's name table, and none had been run. If one comes back FAIL, that is the answer to "why is
# the log empty" and it is worth more than the rest of this file put together.
reset()

import time
from pathlib import Path

import unrealsdk
from bl2_modern import core, mod as pack
from bl2_modern.features import nightlog as N
from unrealsdk.hooks import Type as HookKind

SCRATCH = Path(str(N.FOLDER)).parent / "nights-check"

was = {
    "FOLDER": N.FOLDER,
    "enabled": N.enabled.value,
    "small": N.log_small_pickups.value,
    "times": N.time_kills.value,
    "biggest": N.biggest.value,
    "keep": N.keep_nights.value,
    "file": N._file,
    "bytes": N._bytes,
    "here": N._here,
    "pending": list(N._pending),
    "listeners": list(N.LISTENERS),
    "broken": N._writing_broken,
}


def function_exists(*paths):
    """
    Whether the game really has this function, trying both spellings of the separator.

    Hook strings use `Package.Class:Function`; the object itself is `Package.Class.Function`.
    Returns the spelling that worked, or None.
    """
    for path in paths:
        for candidate in (path.replace(":", "."), path):
            try:
                if unrealsdk.find_object("Function", candidate) is not None:
                    return candidate
            except Exception:
                continue
    return None


class FakeStruct:
    """Stands in for a WrappedStruct. The hook bodies only ever getattr, so this is enough."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeName:
    def __init__(self, name):
        self.Name = name


class FakePawn:
    def __init__(self, name="Skag", player=None):
        self.Class = FakeName(name)
        self.Controller = player

    def GetTargetName(self):
        return self.Class.Name


class FakePlayer:
    def __init__(self, name="Lumi"):
        self.PlayerReplicationInfo = FakeStruct(PlayerName=name)


try:
    # --- do the functions this feature guessed at actually exist ------------------------------
    for label, paths in (
        ("kills - AwardCombatExperience", ("WillowGame.WillowGameInfo:AwardCombatExperience",)),
        ("drops - DropLootOnDeath", ("WillowGame.WillowPawn:DropLootOnDeath",)),
        ("pickups - PickupPickupable", ("WillowGame.WillowPlayerController:PickupPickupable",)),
        (
            "downs - SetupPlayerInjuredState or SetInjuredState",
            (
                "WillowGame.WillowPlayerPawn:SetupPlayerInjuredState",
                "WillowGame.WillowPlayerPawn:SetInjuredState",
            ),
        ),
        (
            "kill timing - TakeDamage on WillowPawn or Pawn",
            ("WillowGame.WillowPawn:TakeDamage", "Engine.Pawn:TakeDamage"),
        ),
    ):
        found = function_exists(*paths)
        check(
            f"the game really has the function this feature watches for {label}",
            found is not None,
            f"found {found}" if found else f"none of {list(paths)} is an object in this game",
        )

    # --- is the feature wired in ---------------------------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "The night's log"), None)
    check(
        "the night's log loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "every hook the feature declares is handed to the pack, so the menu can switch them off",
        feature is not None
        and {id(h) for h in feature.hooks}
        == {id(h) for h in (N.on_kill, N.on_damage, N.on_drop, N.on_pickup, N.on_down,
                            N.on_tick, N.on_character_live)},
        f"{0 if feature is None else len(feature.hooks)} hooks declared",
    )
    check(
        "every one of those hooks is live in this session rather than merely defined",
        all(
            h.get_active_count() == len(h.hook_funcs)
            for h in (N.on_kill, N.on_damage, N.on_drop, N.on_pickup, N.on_down,
                      N.on_tick, N.on_character_live)
        ),
        ", ".join(
            f"{h.__wrapped__.__name__}={h.get_active_count()}/{len(h.hook_funcs)}"
            for h in (N.on_kill, N.on_damage, N.on_drop, N.on_pickup, N.on_down,
                      N.on_tick, N.on_character_live)
        ),
    )
    check(
        "the damage hook really is attached to both spellings, so one wrong guess is survivable",
        sorted(f for f, _t in N.on_damage.hook_funcs)
        == ["Engine.Pawn:TakeDamage", "WillowGame.WillowPawn:TakeDamage"],
        f"{list(N.on_damage.hook_funcs)}",
    )
    check(
        "every hook is a pre-hook, so none of them can change what the game does",
        all(
            t is HookKind.PRE
            for h in (N.on_kill, N.on_damage, N.on_drop, N.on_pickup, N.on_down,
                      N.on_tick, N.on_character_live)
            for _f, t in h.hook_funcs
        ),
        "any POST hook here would be a surprise, not a bug in itself",
    )
    check(
        "all five settings belong to the pack that owns the settings file",
        all(
            o.mod is pack
            for o in (N.enabled, N.log_small_pickups, N.time_kills, N.biggest, N.keep_nights)
        ),
        f"{[getattr(o.mod, 'name', None) for o in (N.enabled, N.log_small_pickups, N.time_kills, N.biggest, N.keep_nights)]}",
    )

    # --- from here on the feature writes into a scratch folder ---------------------------------
    N.FOLDER = SCRATCH
    N.enabled.value = True
    N._writing_broken = False
    N._file = None
    N._bytes = 0
    del N._pending[:]
    N._here = "CheckLand_P"

    # --- every hook body returns None, always --------------------------------------------------
    victim = FakePawn("Skag")
    killer = FakePlayer("Lumi")
    returns = [
        N.on_kill.__wrapped__(
            None, FakeStruct(KilledActor=victim, KillerWPC=killer, TotalExpPoints=120), None, None,
        ),
        N.on_damage.__wrapped__(victim, None, None, None),
        N.on_drop.__wrapped__(victim, None, None, None),
        N.on_pickup.__wrapped__(killer, FakeStruct(Pickup=FakeStruct(Inventory=None)), None, None),
        N.on_down.__wrapped__(FakePawn("Lumi", killer), None, None, None),
        N.on_tick.__wrapped__(None, None, None, None),
        N.on_character_live.__wrapped__(None, None, None, None),
    ]
    check(
        "no hook the log installs can ever block or change what the game was doing",
        set(returns) == {None},
        f"returned {returns!r}",
    )

    # --- a kill is written down, with who and how long ------------------------------------------
    del N._pending[:]
    N._first_hit.clear()
    N.time_kills.value = True
    N.on_damage.__wrapped__(victim, None, None, None)
    N._first_hit[victim] = time.monotonic() - 3.0
    N.on_kill.__wrapped__(
        None, FakeStruct(KilledActor=victim, KillerWPC=killer, TotalExpPoints=120), None, None,
    )
    killed = [e for e in N._pending if e["kind"] == "killed"]
    check(
        "a kill is written down with what died and who killed it",
        len(killed) == 1 and killed[0]["what"] == "Skag" and killed[0]["by"] == "Lumi",
        f"{killed}",
    )
    check(
        "a kill records how long it took, from the first hit",
        killed and 2.5 <= (killed[0]["took_seconds"] or 0) <= 3.6,
        f"took_seconds = {killed[0]['took_seconds'] if killed else None}, faked at 3.0",
    )
    check(
        "the first-hit note is thrown away once the thing is dead, so it cannot pile up",
        victim not in N._first_hit,
        f"{len(N._first_hit)} pawns still remembered",
    )

    N.time_kills.value = False
    N._first_hit.clear()
    N.on_damage.__wrapped__(victim, None, None, None)
    check(
        "with kill timing switched off, nothing is remembered per bullet at all",
        not N._first_hit,
        f"{len(N._first_hit)} entries after a hit with the switch off",
    )
    N.time_kills.value = True

    # --- the extraloot replay guard --------------------------------------------------------------
    import sys

    del N._pending[:]
    replay_module = sys.modules.get("bl2_modern.features.extraloot")
    check(
        "extraloot is loaded, so the guard against its replays has something to look at",
        replay_module is not None,
        "if this fails the guard is dead code, not wrong code",
    )
    if replay_module is not None:
        was_rolling = replay_module._rolling
        replay_module._rolling = True
        N.on_drop.__wrapped__(victim, None, None, None)
        during_replay = len([e for e in N._pending if e["kind"] == "dropped"])
        replay_module._rolling = False
        N.on_drop.__wrapped__(victim, None, None, None)
        after_replay = len([e for e in N._pending if e["kind"] == "dropped"])
        replay_module._rolling = was_rolling
        check(
            "an extra loot roll does not get written down as a second enemy dropping loot",
            during_replay == 0 and after_replay == 1,
            f"{during_replay} written during a replay, {after_replay} after it",
        )

    # --- the small-pickup filter ------------------------------------------------------------------
    class FakeItem:
        def __init__(self, cls, name, rarity=3):
            self.Class = FakeName(cls)
            self.InventoryRarityLevel = rarity
            self._name = name

        def GetTargetName(self):
            return self._name

    del N._pending[:]
    N.log_small_pickups.value = False
    N.on_pickup.__wrapped__(
        killer, FakeStruct(Pickup=FakeStruct(Inventory=FakeItem("WillowUsableItem", "Bullets"))),
        None, None,
    )
    N.on_pickup.__wrapped__(
        killer, FakeStruct(Pickup=FakeStruct(Inventory=FakeItem("WillowWeapon", "Hornet"))),
        None, None,
    )
    picked = [e["what"] for e in N._pending if e["kind"] == "picked up"]
    check(
        "with the small-pickup switch off, ammo is left out and a gun is written down",
        picked == ["Hornet"],
        f"wrote {picked}",
    )

    N.log_small_pickups.value = True
    del N._pending[:]
    N.on_pickup.__wrapped__(
        killer, FakeStruct(Pickup=FakeStruct(Inventory=FakeItem("WillowUsableItem", "Bullets"))),
        None, None,
    )
    check(
        "with the small-pickup switch on, the ammo goes in too",
        [e["what"] for e in N._pending if e["kind"] == "picked up"] == ["Bullets"],
        f"{N._pending}",
    )

    # --- two hooks, one down ----------------------------------------------------------------------
    del N._pending[:]
    N._last_down.clear()
    downed = FakePawn("Lumi", killer)
    N.on_down.__wrapped__(downed, None, None, None)
    N.on_down.__wrapped__(downed, None, None, None)
    check(
        "both spellings of the down hook firing for one knockdown counts as one knockdown",
        len([e for e in N._pending if e["kind"] == "went down"]) == 1,
        f"{[e for e in N._pending if e['kind'] == 'went down']}",
    )

    # --- listeners hear everything, even with the file switched off ---------------------------------
    heard = []
    N.LISTENERS.append(heard.append)
    N.enabled.value = False
    del N._pending[:]
    N.note("killed", what="Skag", by="Lumi")
    check(
        "with the log's file switched off, listeners still hear the event",
        len(heard) == 1 and heard[0]["kind"] == "killed",
        f"{heard}",
    )
    check(
        "with the log's file switched off, nothing is queued for writing",
        not N._pending,
        f"{N._pending}",
    )

    def deaf(_event):
        raise RuntimeError("this listener is broken")

    N.LISTENERS.append(deaf)
    escaped = None
    try:
        N.note("killed", what="Skag")
    except Exception as ex:
        escaped = ex
    check(
        "one broken listener cannot stop the log, or an enemy from dying",
        escaped is None,
        f"{escaped!r}" if escaped else "nothing escaped",
    )
    N.LISTENERS.remove(deaf)
    N.LISTENERS.remove(heard.append)

    # --- the file itself ----------------------------------------------------------------------------
    N.enabled.value = True
    N._file = None
    N._bytes = 0
    del N._pending[:]
    N.note("killed", what="Skag", by="Lumi")
    N._flush()
    written = N._file
    check(
        "flushing actually leaves a file on disk",
        written is not None and written.is_file(),
        f"{written}",
    )
    text = written.read_text(encoding="utf-8") if written and written.is_file() else ""
    lines = [line for line in text.splitlines() if line.strip()]
    check(
        "the first line of a night says whether this machine can see kills at all",
        lines and '"kind": "night began"' in lines[0],
        f"first line was: {lines[0][:120] if lines else '(no lines)'}",
    )
    # EVERY line, not "there are exactly two". This wanted a line count, and the count depends on
    # how many events the checks above happened to write - so it failed for the file holding more
    # of what it is supposed to hold. What matters is that no line is ever half an object: the
    # file is read back later a line at a time, and one broken line would cost the whole night.
    _json = __import__("json")
    parsed, broken = [], []
    for line in lines:
        try:
            parsed.append(_json.loads(line))
        except Exception as ex:  # noqa: BLE001, PERF203
            broken.append(f"{line[:60]}... {ex!r}")
    check(
        "every event is one whole line of json, and every one of them parses",
        not broken and len(parsed) == len(lines),
        f"{len(lines)} lines, {len(broken)} would not parse: {broken[:2]}",
    )
    check(
        "the kill that was just recorded is in there",
        any(event.get("what") == "Skag" for event in parsed),
        f"{[event.get('kind') for event in parsed]}",
    )

    # --- rolling, without writing five megabytes ------------------------------------------------------
    before_roll = N._file
    N.biggest.value = 1
    N._bytes = 1 * 1024 * 1024
    N.note("killed", what="Skag")
    N._flush()
    check(
        "a full file is closed and the night carries on in a new part",
        N._file != before_roll and "part2" in N._file.name,
        f"was {before_roll.name}, now {N._file.name}",
    )
    N.note("killed", what="Bullymong")
    N._flush()
    check(
        "the new part is a real file that got written to",
        N._file.is_file() and "Bullymong" in N._file.read_text(encoding="utf-8"),
        f"{N._file}",
    )

    # --- pruning ------------------------------------------------------------------------------------
    for index in range(6):
        made = SCRATCH / f"night-2000-01-0{index + 1}-0000.jsonl"
        made.write_text("{}\n", encoding="utf-8")
    N.keep_nights.value = 3
    N._prune()
    left = sorted(p.name for p in SCRATCH.glob("night-*.jsonl"))
    check(
        "the oldest files are deleted once there are more than the player asked to keep",
        len(left) == 3,
        f"{len(left)} left: {left}",
    )
    check(
        "pruning keeps the newest, not an arbitrary three",
        all(name.startswith("night-2") for name in left) and "night-2000-01-01-0000.jsonl" not in left,
        f"{left}",
    )

    # --- a folder it cannot write to switches the log off rather than raising ---------------------------
    N._writing_broken = False
    N.FOLDER = Path("Z:/no-such-drive/nights")
    N._file = None
    del N._pending[:]
    N.note("killed", what="Skag")
    escaped = None
    try:
        N._flush()
    except Exception as ex:
        escaped = ex
    check(
        "a folder that cannot be written to never raises into the frame the game is drawing",
        escaped is None,
        f"{escaped!r}" if escaped else "nothing escaped",
    )
    check(
        "a folder that cannot be written to switches the log off for the run instead of retrying",
        N._writing_broken is True,
        f"_writing_broken = {N._writing_broken}",
    )

    # --- a hook handed nonsense --------------------------------------------------------------------
    N._writing_broken = False
    N.FOLDER = SCRATCH
    escaped = []
    for name, hook_object, arguments in (
        ("kill", N.on_kill, (None, FakeStruct(), None, None)),
        ("damage", N.on_damage, (None, None, None, None)),
        ("drop", N.on_drop, (None, None, None, None)),
        ("pickup", N.on_pickup, (None, FakeStruct(), None, None)),
        ("down", N.on_down, (None, None, None, None)),
        ("tick", N.on_tick, (None, None, None, None)),
        ("spawn", N.on_character_live, (None, None, None, None)),
    ):
        try:
            hook_object.__wrapped__(*arguments)
        except Exception as ex:
            escaped.append(f"{name}: {ex!r}")
    check(
        "every hook survives being handed nothing at all, which is what a wrong guess looks like",
        not escaped,
        "; ".join(escaped) or "all seven survived",
    )

finally:
    for path in sorted(SCRATCH.glob("*")) if SCRATCH.is_dir() else []:
        try:
            path.unlink()
        except Exception:
            pass
    try:
        SCRATCH.rmdir()
    except Exception:
        pass

    N.FOLDER = was["FOLDER"]
    N.enabled.value = was["enabled"]
    N.log_small_pickups.value = was["small"]
    N.time_kills.value = was["times"]
    N.biggest.value = was["biggest"]
    N.keep_nights.value = was["keep"]
    N._file = was["file"]
    N._bytes = was["bytes"]
    N._here = was["here"]
    N._writing_broken = was["broken"]
    del N._pending[:]
    N._pending.extend(was["pending"])
    del N.LISTENERS[:]
    N.LISTENERS.extend(was["listeners"])
    N._first_hit.clear()
    N._last_down.clear()

    check(
        "everything this file changed has been put back",
        N.FOLDER == was["FOLDER"]
        and N.enabled.value == was["enabled"]
        and N.biggest.value == was["biggest"]
        and N.keep_nights.value == was["keep"]
        and list(N.LISTENERS) == was["listeners"]
        and not SCRATCH.exists(),
        f"folder={N.FOLDER} enabled={N.enabled.value} listeners={len(N.LISTENERS)} "
        f"scratch still there={SCRATCH.exists()}",
    )

summary()
