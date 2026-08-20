# Extra loot roll per player - checks for the claims in AUDIT-RAW/extra-loot-roll-per-player.md
# Run: bash bl2-mcp/tools/ask.sh bl2-mcp/tools/checks/extra-loot-roll-per-player.py
#
# Nothing in here touches the world. Every check drives the hook's own callback
# (on_loot_dropped.__wrapped__) with a stand-in `func` and counts how many times that stand-in is
# called. The arithmetic, the re-entrancy guard, the self-disable and the "returns None so the
# original drop still happens" claim are all decidable that way, in any map, with nobody dying.
#
# The claims that genuinely need an enemy - does a re-roll put guns on the floor, are they
# DIFFERENT guns - are in extra-loot-roll-per-player-needs-travel.py, because they need a map with
# something alive in it.
#
# One difference from the audit's own probes worth knowing: the audit counts hook ENTRIES by
# spying on WillowPawn:DropLootOnDeath, so its expected number is `1 + (N-1)*R` - the 1 being the
# enemy's own original call. This file calls the hook body itself and counts only the replays, so
# the expected number here is exactly (N-1)*R.
reset()

import json

from bl2_modern import core, mod as pack
from bl2_modern.features import extraloot as X
from unrealsdk.hooks import Type as HookKind

# Everything this file is allowed to change, remembered before it changes any of it.
was_enabled = X.enabled.value
was_rolls = X.rolls_each.value
real_player_count = X._player_count
real_get_pc = X.get_pc

calls = []


def counting(*args, **kwargs):
    calls.append(args)


def refusing(*args, **kwargs):
    """A game that takes the call and then says no - the case extraloot.py:84 exists for."""
    calls.append(args)
    raise RuntimeError("the game refused the extra roll")


def fire(func=counting, players=None, rolls=None):
    """Run the hook body once. Returns (how many extra rolls it asked for, what it returned)."""
    if players is not None:
        X._player_count = lambda: players
    if rolls is not None:
        X.rolls_each.value = rolls
    del calls[:]
    X._rolling = False
    returned = X.on_loot_dropped.__wrapped__(None, None, None, func)
    return len(calls), returned


def as_int(value):
    """Unreal enums come back as several different shapes; -1 means it could not be read."""
    try:
        return int(getattr(value, "value", value))
    except Exception as ex:  # noqa: BLE001
        return -1


try:
    # --- is the feature actually wired in at all --------------------------------------------
    feature = next((f for f in core.all_features() if f.name == "Extra loot roll per player"), None)
    check(
        "the extra-loot feature loaded into the pack without failing",
        feature is not None and feature.failed is None,
        "not registered at all" if feature is None else (feature.failed or "registered, no failure"),
    )
    check(
        "the loot hook is attached to WillowPawn:DropLootOnDeath as a pre-hook",
        list(X.on_loot_dropped.hook_funcs) == [("WillowGame.WillowPawn:DropLootOnDeath", HookKind.PRE)],
        f"{list(X.on_loot_dropped.hook_funcs)}",
    )
    check(
        "the loot hook is live in this session, not merely defined",
        X.on_loot_dropped.get_active_count() == 1,
        f"{X.on_loot_dropped.get_active_count()} of 1 hooks active",
    )
    check(
        "the hook object the pack enables is the one this feature file built",
        any(h is X.on_loot_dropped for h in pack.hooks),
        f"{len(pack.hooks)} hooks in the pack",
    )
    check(
        "both of the feature's dials belong to the pack that owns the settings file",
        X.enabled.mod is pack and X.rolls_each.mod is pack,
        f"enabled.mod={getattr(X.enabled.mod, 'name', None)!r} "
        f"rolls_each.mod={getattr(X.rolls_each.mod, 'name', None)!r}",
    )

    # --- how many players the game thinks there are (claim 10) -------------------------------
    # MEASURED 2026-08-19 and written here as a regression guard, not an investigation: solo,
    # _player_count() is 1 and PRIArray holds exactly one entry. The theory that PRIArray could
    # be empty and the max(1, ...) clamp could be papering over a zero is disproved.
    solo_count = X._player_count()
    try:
        pris = list(pc().WorldInfo.GRI.PRIArray)
        pri_names = [str(p.PlayerName) for p in pris]
    except Exception as ex:  # noqa: BLE001
        pris, pri_names = None, [f"unreadable: {ex!r}"]

    check(
        "a solo session counts exactly one player",
        solo_count == 1,
        f"_player_count() = {solo_count}",
    )
    check(
        "the world's own player list holds one entry solo, so the count is not clamped up from zero",
        pris is not None and len(pris) == 1,
        f"PRIArray = {pri_names}",
    )
    check(
        "the count the feature uses is the length of that list, not a fallback",
        pris is not None and solo_count == len(pris),
        f"_player_count() = {solo_count}, len(PRIArray) = {None if pris is None else len(pris)}",
    )

    X.get_pc = lambda: (_ for _ in ()).throw(RuntimeError("no session yet"))
    count_without_a_controller = X._player_count()
    X.get_pc = real_get_pc
    check(
        "the player count answers 1 rather than raising when there is no player controller",
        count_without_a_controller == 1,
        f"got {count_without_a_controller} with get_pc raising (extraloot.py:57-61)",
    )

    # --- claim 1: solo, the feature does nothing ---------------------------------------------
    X.enabled.value = True
    X._player_count = real_player_count
    solo_rolls = {}
    for setting in (1, 2, 3, 4, 5):
        solo_rolls[setting], _ = fire(rolls=setting)
    check(
        "solo, the feature asks for no extra rolls at any slider setting",
        set(solo_rolls.values()) == {0},
        f"rolls-per-extra-player {solo_rolls} (real player count, no faking)",
    )
    check(
        "solo, the re-entrancy flag is never even set",
        X._rolling is False,
        f"_rolling = {X._rolling}",
    )

    X.enabled.value = False
    off_rolls, _ = fire(players=4, rolls=5)
    check(
        "with the option switched off nothing happens even in a full party",
        off_rolls == 0,
        f"{off_rolls} extra rolls with the option off and the count faked to 4",
    )

    # --- claim 5: (N-1)*R rolls, no more and no fewer ----------------------------------------
    X.enabled.value = True
    for players, rolls in ((1, 5), (2, 1), (2, 3), (3, 2), (4, 1), (5, 5)):
        expected = (players - 1) * rolls
        got, _ = fire(players=players, rolls=rolls)
        check(
            f"a party of {players} at {rolls} rolls each asks for {expected} extra rolls",
            got == expected,
            f"got {got} - the player count is FAKED here, so this tests the code path and "
            f"not real co-op",
        )

    # --- claim 6: the re-entrancy guard ------------------------------------------------------
    depth = []

    def reentrant(*args, **kwargs):
        """What the real game does: a call into a hooked function comes back through the hook."""
        depth.append(1)
        if len(depth) < 50:  # a fuse - a broken guard must not hang the frame the bridge runs in
            X.on_loot_dropped.__wrapped__(None, None, None, reentrant)

    X._player_count = lambda: 2
    X.rolls_each.value = 1
    X._rolling = False
    X.on_loot_dropped.__wrapped__(None, None, None, reentrant)
    check(
        "our own replays do not re-trigger the hook forever",
        len(depth) == 1,
        f"{len(depth)} nested rolls before the fuse at 50 (faked 2 players, 1 roll each)",
    )
    check(
        "the re-entrancy flag is left clear once a normal run finishes",
        X._rolling is False,
        f"_rolling = {X._rolling}",
    )

    # --- claim 7: the pre-hook never blocks the enemy's own drop ------------------------------
    # Per sdk_mods/.stubs/unrealsdk/hooks/__init__.pyi, only the Block sentinel stops the game's
    # function running; anything else - and None in particular - lets it through. So the code-level
    # half of this claim is "all three exits return None". The world-level half needs an enemy and
    # lives in the -needs-travel file.
    X.enabled.value = False
    _, ret_off = fire()
    X.enabled.value = True
    _, ret_solo = fire(players=1, rolls=5)
    _, ret_rolled = fire(players=2, rolls=2)
    check(
        "the hook lets the enemy's own loot through on every exit it has",
        ret_off is None and ret_solo is None and ret_rolled is None,
        f"switched off -> {ret_off!r}, nothing to add -> {ret_solo!r}, after rolling -> {ret_rolled!r}",
    )

    # --- claim 8: a refused call switches the feature off ------------------------------------
    # SWITCHED ON, ON DISK, FIRST. The file records False already - the feature ships off - so
    # turning it on only in memory meant the "did the off switch reach the file" check below was
    # comparing a file that said False against a file that said False and calling it untouched.
    # It could not pass however the code behaved. Saving True first gives the later save
    # something to actually change.
    try:
        settings_pristine = pack.settings_file.read_text(encoding="utf-8")
    except Exception as ex:  # noqa: BLE001
        settings_pristine = f"unreadable: {ex!r}"
    X.enabled.value = True
    try:
        pack.save_settings()
    except Exception as ex:  # noqa: BLE001
        print(f"   (could not save the on state first: {ex!r})")
    try:
        settings_before = pack.settings_file.read_text(encoding="utf-8")
    except Exception as ex:  # noqa: BLE001
        settings_before = f"unreadable: {ex!r}"
    escaped = None
    try:
        refused_rolls, _ = fire(func=refusing, players=2, rolls=3)
    except Exception as ex:  # noqa: BLE001
        escaped, refused_rolls = ex, -1
    check(
        "a refused roll never lets its exception out into the enemy's death path",
        escaped is None,
        f"{escaped!r}" if escaped else "nothing escaped",
    )
    check(
        "a refused roll switches the feature off",
        X.enabled.value is False,
        f"enabled.value = {X.enabled.value}",
    )
    check(
        "one refusal abandons the remaining rolls instead of retrying them",
        refused_rolls == 1,
        f"{refused_rolls} calls attempted out of 3 asked for",
    )
    check(
        "a refusal leaves the re-entrancy flag clear, so the feature is not permanently inert",
        X._rolling is False,
        f"_rolling = {X._rolling}",
    )

    # --- claim 9 / suspected bug 2: does the off switch survive a restart --------------------
    # The refusal above set enabled.value to False AND is supposed to write that to disk, so a
    # feature that turned itself off because the game refused the call does not come back on next
    # launch and get refused again on every single death, forever. The static half is in the
    # -files.py file.
    try:
        settings_after = pack.settings_file.read_text(encoding="utf-8")
    except Exception as ex:  # noqa: BLE001
        settings_after = f"unreadable: {ex!r}"

    def option_on_disk(text):
        try:
            return json.loads(text).get("options", {}).get(X.enabled.identifier)
        except Exception as ex:  # noqa: BLE001
            return f"unreadable: {ex!r}"

    on_disk_now = option_on_disk(settings_after)
    on_disk_at_start = option_on_disk(settings_pristine)
    check(
        "switching itself off reaches the settings file, so it stays off next launch",
        settings_after != settings_before and on_disk_now is False,
        f"the file still records {on_disk_now!r} after the feature turned itself off in memory; "
        f"file {'changed' if settings_after != settings_before else 'untouched'}",
    )
    check(
        "the feature has not silently switched itself off since the settings file was written",
        was_enabled == on_disk_at_start,
        f"live value at the start of this file was {was_enabled!r}, the file says "
        f"{on_disk_at_start!r}",
    )

    # --- claim 12: an enemy dying can never fail because of this feature -----------------------
    # Working out how many extra rolls to make reads the player list and an option, and it used
    # to sit OUTSIDE the try - so anything thrown there went straight into the game's death path.
    # It is inside now. The real _player_count has its own guard (checked above), which is why
    # this needs a monkeypatch to reach at all, but a guard is always one edit away from lost.
    X.enabled.value = True
    X._player_count = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    broke_out = None
    try:
        X.on_loot_dropped.__wrapped__(None, None, None, counting)
    except Exception as ex:  # noqa: BLE001
        broke_out = ex
    X._player_count = real_player_count
    check(
        "a broken player count cannot stop an enemy from dying",
        broke_out is None,
        f"{broke_out!r} escaped the hook - the try at extraloot.py:81 covers only the roll loop, "
        f"not the arithmetic at :76",
    )

    # --- claim 11: host-only, by nature -------------------------------------------------------
    # Solo this can only establish the baseline: we are the authority, so any loot rolled here is
    # real. It fails if this file is ever run on a machine that JOINED someone else's game - which
    # is the case the feature has no guard for (nothing in extraloot.py mentions NetMode or Role).
    try:
        net_mode = as_int(pc().WorldInfo.NetMode)
        role = as_int(pc().Role)
    except Exception:  # noqa: BLE001 - -1 fails the check, which is the honest answer
        net_mode, role = -1, -1
    check(
        "this session is the host, so loot rolled here is loot that really exists",
        net_mode in (0, 1, 2) and role == 3,
        f"NetMode={net_mode} (3 would be a client), Role={role} (3 is authority)",
    )

finally:
    X._player_count = real_player_count
    X.get_pc = real_get_pc
    X.enabled.value = was_enabled
    X.rolls_each.value = was_rolls
    X._rolling = False
    check(
        "everything this file changed has been put back",
        X.enabled.value == was_enabled
        and X.rolls_each.value == was_rolls
        and X._player_count is real_player_count
        and X.get_pc is real_get_pc
        and X._rolling is False,
        f"enabled={X.enabled.value} rolls={X.rolls_each.value} _rolling={X._rolling}",
    )

summary()
